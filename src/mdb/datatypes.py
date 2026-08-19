"""Value decoding: ``omfi:*`` data types.

Every TOC entry names its type, and the file's own schema registry resolves
that number to a name such as ``omfi:ObjRefArray``.  Decoding is therefore
driven by the file rather than by hard-coded property tables, which is what
keeps the reader working when Media Composer adds properties.

Unknown types fall through to :class:`Opaque`, so a new type never breaks a
parse -- you still get the raw bytes, the type name and the owning object.
"""
from __future__ import annotations

import datetime
import struct
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from .mobid import MobID, ShortUID

__all__ = [
    "Opaque", "Rational", "MobIndexEntry", "OffsetLength", "SMPTELabel",
    "decode", "DECODERS", "register_decoder", "known_types",
]


# --------------------------------------------------------------------------
# small value objects
# --------------------------------------------------------------------------
class Opaque(object):
    """Bytes we could decode structurally but not interpret semantically."""

    __slots__ = ("type_name", "raw")

    def __init__(self, type_name: str, raw: bytes):
        self.type_name = type_name
        self.raw = bytes(raw)

    def __bytes__(self):
        return self.raw

    def __len__(self):
        return len(self.raw)

    def __eq__(self, other):
        if isinstance(other, Opaque):
            return self.raw == other.raw and self.type_name == other.type_name
        if isinstance(other, (bytes, bytearray)):
            return self.raw == bytes(other)
        return NotImplemented

    def __hash__(self):
        return hash((self.type_name, self.raw))

    def hex(self) -> str:
        return self.raw.hex()

    def as_text(self, encoding: str = "utf-8") -> str:
        """Best-effort text reading -- several Avid blobs are stuffed strings."""
        return self.raw.rstrip(b"\0").decode(encoding, "replace")

    def __repr__(self):
        return "<%s %d bytes %s>" % (self.type_name, len(self.raw), self.raw[:16].hex())


class Rational(NamedTuple):
    """``omfi:ExactEditRate`` / ``omfi:Rational``: numerator over denominator."""

    numerator: int
    denominator: int

    def __float__(self):
        return self.numerator / self.denominator if self.denominator else float("nan")

    def __str__(self):
        return "%d/%d" % (self.numerator, self.denominator)


class MobIndexEntry(NamedTuple):
    """One record of HEAD's ``omfi:MobIndex`` fast-lookup table.

    The record is 20 bytes: a 12-byte short UID, a **32-bit** object ID, and a
    trailing 32-bit field.  That last word is zero throughout ``SourceMobs``
    but carries a constant non-zero value in ``CompositionMobs`` (one value per
    file, repeated on every record), so reading the reference as a 64-bit
    integer silently corrupts every composition-mob lookup.  The meaning of
    ``extra`` is not known [?]; it is preserved rather than discarded.
    """

    uid: ShortUID
    object_id: int
    extra: int = 0


class OffsetLength(NamedTuple):
    """Bento's ``0x13`` type: a region of the file, carried in the entry itself."""

    offset: int
    length: int


class SMPTELabel(object):
    """A 16-byte SMPTE Universal Label stored in AAF's half-swapped AUID form.

    AAF serialises a UL as ``{uint32 Data1; uint16 Data2; uint16 Data3;
    uint8 Data4[8]}`` with the two halves exchanged, so the recognisable
    ``06 0e 2b 34`` prefix turns up at byte 8.  :attr:`ul` puts it back in
    canonical SMPTE order.
    """

    __slots__ = ("raw",)

    def __init__(self, raw: bytes):
        if len(raw) != 16:
            raise ValueError("GUID must be 16 bytes, got %d" % len(raw))
        self.raw = bytes(raw)

    @property
    def is_swapped_ul(self) -> bool:
        return self.raw[8:12] == bytes.fromhex("060e2b34")

    @property
    def ul(self) -> bytes:
        """Canonical 16-byte SMPTE UL byte order."""
        if not self.is_swapped_ul:
            return self.raw
        d1, d2, d3 = struct.unpack_from("<IHH", self.raw, 0)
        return self.raw[8:16] + struct.pack(">IHH", d1, d2, d3)

    @property
    def urn(self) -> str:
        ul = self.ul
        return "urn:smpte:ul:" + ".".join(ul[i:i + 4].hex() for i in range(0, 16, 4))

    def __eq__(self, other):
        if isinstance(other, SMPTELabel):
            return self.raw == other.raw
        if isinstance(other, (bytes, bytearray)):
            return self.raw == bytes(other)
        return NotImplemented

    def __hash__(self):
        return hash(self.raw)

    def __str__(self):
        return self.urn if self.is_swapped_ul else self.raw.hex()

    def __repr__(self):
        return "<SMPTELabel %s>" % self


# --------------------------------------------------------------------------
# primitive readers
# --------------------------------------------------------------------------
def _int(signed: bool, size: int) -> Callable[[bytes, str], int]:
    codes = {1: "b", 2: "h", 4: "i", 8: "q"}
    code = codes[size]
    if not signed:
        code = code.upper()

    def read(raw: bytes, endian: str) -> int:
        if len(raw) < size:
            # tolerate short-written integers: pad rather than fail the parse
            raw = raw + b"\0" * (size - len(raw)) if endian == "<" \
                else b"\0" * (size - len(raw)) + raw
        return struct.unpack_from(endian + code, raw, 0)[0]
    return read


def _string(raw: bytes, endian: str) -> str:
    """``omfi:String``: NUL-terminated.

    Legacy code-page and ``*UTF8`` twins of the same property coexist, so both
    are decoded permissively; the UTF8 variant is the one to prefer.
    """
    return raw.split(b"\0", 1)[0].decode("utf-8", "replace")


def _boolean(raw: bytes, endian: str) -> bool:
    return bool(raw and raw[0])


def _object_tag(raw: bytes, endian: str) -> str:
    """A 4CC, stored in reading order even inside an immediate."""
    return raw.rstrip(b"\0").decode("latin-1")


def _byte_order(raw: bytes, endian: str) -> str:
    """``OMFI:ByteOrder`` is typed ``omfi:Short`` but reads as ``II`` / ``MM``."""
    return raw.decode("latin-1")


def _objref(raw: bytes, endian: str) -> int:
    if len(raw) < 8:
        raw = raw.ljust(8, b"\0")
    return struct.unpack_from(endian + "Q", raw, 0)[0]


def _objref_array(raw: bytes, endian: str) -> List[int]:
    if len(raw) < 2:
        return []
    count, = struct.unpack_from(endian + "H", raw, 0)
    out = []
    for i in range(count):
        off = 2 + 8 * i
        if off + 8 > len(raw):
            break
        out.append(struct.unpack_from(endian + "Q", raw, off)[0])
    return out


def _mob_index(raw: bytes, endian: str) -> List[MobIndexEntry]:
    if len(raw) < 2:
        return []
    count, = struct.unpack_from(endian + "H", raw, 0)
    out = []
    for i in range(count):
        off = 2 + 20 * i
        if off + 20 > len(raw):
            break
        rec = raw[off:off + 20]
        object_id, extra = struct.unpack_from(endian + "II", rec, 12)
        out.append(MobIndexEntry(ShortUID(rec[:12]), object_id, extra))
    return out


def _uid(raw: bytes, endian: str):
    """``omfi:UID`` is a 32-byte UMID on mobs and a 12-byte short UID on SCLPs."""
    if len(raw) == 32:
        return MobID(raw)
    if len(raw) == 12:
        return ShortUID(raw)
    return Opaque("omfi:UID", raw)


def _rational(raw: bytes, endian: str) -> Rational:
    if len(raw) < 8:
        return Rational(*struct.unpack(endian + "2i", raw.ljust(8, b"\0")))
    return Rational(*struct.unpack_from(endian + "2i", raw, 0))


def _timestamp(raw: bytes, endian: str):
    """Unix seconds, plus a trailing flag byte in the 5-byte ``MOBJ`` variant.

    Returns ``None`` for the all-zero stamps Media Composer writes when it has
    no time to record, so callers can distinguish "unset" from "the epoch".
    """
    if not raw or not any(raw):
        return None
    secs, = struct.unpack_from(endian + "I", raw.ljust(4, b"\0"), 0)
    try:
        return datetime.datetime.fromtimestamp(secs, datetime.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return Opaque("omfi:TimeStamp", raw)


def _version(raw: bytes, endian: str) -> Tuple[int, int]:
    """``omfi:VersionType``: a pair of bytes, major then minor."""
    b = raw.ljust(2, b"\0")
    return (b[0], b[1])


def _guid(raw: bytes, endian: str):
    if len(raw) == 16:
        return SMPTELabel(raw)
    return Opaque("omfi:GUID", raw)


def _int_array(size: int, signed: bool = True):
    code = {1: "b", 2: "h", 4: "i", 8: "q"}[size]
    if not signed:
        code = code.upper()

    def read(raw: bytes, endian: str) -> List[int]:
        n = len(raw) // size
        return list(struct.unpack_from(endian + "%d%s" % (n, code), raw, 0)) if n else []
    return read


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------
DECODERS: Dict[str, Callable[[bytes, str], Any]] = {
    # integers
    "omfi:Char":              _int(True, 1),
    "omfi:Uchar":             _int(False, 1),
    "omfi:Short":             _int(True, 2),
    "omfi:Ushort":            _int(False, 2),
    "omfi:Long":              _int(True, 4),
    "omfi:Ulong":             _int(False, 4),
    "omfi:Int32":             _int(True, 4),
    "omfi:UInt32":            _int(False, 4),
    "omfi:Int64":             _int(True, 8),
    "omfi:UInt64":            _int(False, 8),
    "omfi:Boolean":           _boolean,
    # enumerations -- kept numeric here; see mdb.enums for the labels
    "omfi:AttrKind":          _int(False, 2),
    "omfi:TrackType":         _int(False, 2),
    "omfi:PhysicalMobType":   _int(False, 2),
    "omfi:UsageCodeType":     _int(False, 4),
    "omfi:ColorSitingType":   _int(False, 2),
    "omfi:LayoutType":        _int(False, 2),
    "omfi:EdgeType":          _int(False, 2),
    "omfi:CharSetType":       _int(False, 2),
    "omfi:JPEGTableIDType":   _int(False, 4),
    # aggregates
    "omfi:ObjRef":            _objref,
    "omfi:ObjRefArray":       _objref_array,
    "omfi:MobIndex":          _mob_index,
    "omfi:Int32Array":        _int_array(4),
    # identity and text
    "omfi:UID":               _uid,
    "omfi:GUID":              _guid,
    "omfi:String":            _string,
    "omfi:ObjectTag":         _object_tag,
    # time and rates
    "omfi:ExactEditRate":     _rational,
    "omfi:Rational":          _rational,
    "omfi:TimeStamp":         _timestamp,
    "omfi:VersionType":       _version,
    # floats
    "omfi:Double":            lambda raw, e: struct.unpack_from(e + "d", raw.ljust(8, b"\0"), 0)[0],
    "omfi:Float":             lambda raw, e: struct.unpack_from(e + "f", raw.ljust(4, b"\0"), 0)[0],
}

#: properties that carry a decoder of their own regardless of declared type
PROPERTY_DECODERS: Dict[str, Callable[[bytes, str], Any]] = {
    "OMFI:ByteOrder": _byte_order,
}


def register_decoder(type_name: str, fn: Callable[[bytes, str], Any]) -> None:
    """Teach the reader a new ``omfi:*`` type without subclassing anything."""
    DECODERS[type_name] = fn


def known_types() -> List[str]:
    return sorted(DECODERS)


def decode(type_name: str, raw: bytes, endian: str = "<",
           property_name: Optional[str] = None) -> Any:
    """Decode ``raw`` according to its OMF type name.

    Unknown types return :class:`Opaque` rather than raising -- the schema
    evolves, and a value we cannot name is still worth handing back.
    """
    if property_name is not None:
        special = PROPERTY_DECODERS.get(property_name)
        if special is not None:
            return special(raw, endian)
    fn = DECODERS.get(type_name)
    if fn is None:
        return Opaque(type_name, raw)
    try:
        return fn(raw, endian)
    except Exception:
        return Opaque(type_name, raw)
