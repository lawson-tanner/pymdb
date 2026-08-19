"""MobIDs -- the universal join key.

The same material keeps the same MobID across MDB, AVB, AAF and MXF, so
matching MobIDs is a first-class operation: MSML (volume links), MCBR (bin
links) and MCMR (mob references) all carry a *copy* of a MobID rather than an
object reference.

Two representations appear in an MDB:

``MobID``
    the full 32-byte SMPTE UMID stored under ``OMFI:MOBJ:MobID``, prefixed
    ``06 0a 2b 34 01 01 01 05 01 01 0f 10``.

``ShortUID``
    the legacy OMF1 12-byte identifier (three uint32s) used by ``SCLP:SourceID``
    and by HEAD's MobIndex fast-lookup tables.  In this format its first word is
    always 42 and its last eight bytes equal bytes 16-23 of the full UMID --
    which is what lets you join the two.
"""
from __future__ import annotations

import struct
from typing import Optional

__all__ = ["MobID", "ShortUID", "SMPTE_UMID_PREFIX", "NULL_SHORT_UID"]

SMPTE_UMID_PREFIX = bytes.fromhex("060a2b34010101050101 0f10".replace(" ", ""))

#: OMF1's "no source" sentinel: three zero words
NULL_SHORT_UID = b"\0" * 12


class ShortUID(object):
    """A 12-byte OMF1 mob identifier: three little-endian uint32s."""

    __slots__ = ("_raw",)

    def __init__(self, raw: bytes):
        if len(raw) != 12:
            raise ValueError("short UID must be 12 bytes, got %d" % len(raw))
        self._raw = bytes(raw)

    @classmethod
    def from_words(cls, prefix: int, major: int, minor: int) -> "ShortUID":
        return cls(struct.pack("<3I", prefix, major, minor))

    @property
    def bytes(self) -> bytes:
        return self._raw

    @property
    def words(self):
        return struct.unpack("<3I", self._raw)

    @property
    def prefix(self) -> int:
        """First word -- always 42 (0x2A) in Avid MDBs."""
        return struct.unpack_from("<I", self._raw, 0)[0]

    @property
    def material(self) -> bytes:
        """The 8 bytes that match a full UMID's material number (UMID[16:24])."""
        return self._raw[4:12]

    @property
    def is_null(self) -> bool:
        """OMF1's 0-0-0 sentinel: the end of a derivation chain."""
        return self._raw == NULL_SHORT_UID

    def matches(self, mob_id: "MobID") -> bool:
        return isinstance(mob_id, MobID) and mob_id.material == self.material

    def __eq__(self, other):
        if isinstance(other, ShortUID):
            return self._raw == other._raw
        if isinstance(other, (bytes, bytearray)):
            return self._raw == bytes(other)
        return NotImplemented

    def __hash__(self):
        return hash(self._raw)

    def __str__(self):
        a, b, c = self.words
        return "%d-%d-%d" % (a, b, c)

    def __repr__(self):
        return "<ShortUID %s>" % self


class MobID(object):
    """A 32-byte SMPTE UMID.

    Layout (SMPTE 330M): 12-byte universal label, 1-byte length, 3-byte
    instance number, 16-byte material number.  Avid stores the material number
    as ``material`` (8 bytes, matching the OMF1 short UID) followed by an 8-byte
    tail; both are exposed.
    """

    __slots__ = ("_raw",)

    def __init__(self, raw: bytes):
        if len(raw) != 32:
            raise ValueError("MobID must be 32 bytes, got %d" % len(raw))
        self._raw = bytes(raw)

    @classmethod
    def from_hex(cls, text: str) -> "MobID":
        return cls(bytes.fromhex(text.replace("-", "").replace(" ", "")))

    @property
    def bytes(self) -> bytes:
        return self._raw

    @property
    def label(self) -> bytes:
        """The 12-byte universal label."""
        return self._raw[:12]

    @property
    def is_smpte_umid(self) -> bool:
        """True for any SMPTE 330M UMID label, not just one generation method.

        Media Composer writes two variants: ``...01 01 01 05 01 01 0f 10`` on
        most mobs and ``...01 01 01 00 01 01 0f 00`` on the tape-side source
        mobs.  Bytes 7 and 11 are the specification version and the material
        generation method, so both are legitimate and only the fixed part of
        the label is checked here.
        """
        r = self._raw
        return r[:7] == SMPTE_UMID_PREFIX[:7] and r[8:11] == SMPTE_UMID_PREFIX[8:11]

    @property
    def spec_version(self) -> int:
        """UMID label byte 7 -- the SMPTE specification version."""
        return self._raw[7]

    @property
    def material_generation(self) -> int:
        """UMID label byte 11 -- how the material number was generated."""
        return self._raw[11]

    @property
    def length(self) -> int:
        return self._raw[12]

    @property
    def instance(self) -> int:
        return int.from_bytes(self._raw[13:16], "big")

    @property
    def material(self) -> bytes:
        """UMID[16:24] -- the 8 bytes shared with the OMF1 short UID."""
        return self._raw[16:24]

    @property
    def short_uid(self) -> ShortUID:
        """The OMF1 short UID this MobID would appear as in a MobIndex."""
        return ShortUID(struct.pack("<I", 42) + self.material)

    @property
    def is_null(self) -> bool:
        return self._raw == b"\0" * 32

    def __eq__(self, other):
        if isinstance(other, MobID):
            return self._raw == other._raw
        if isinstance(other, (bytes, bytearray)):
            return self._raw == bytes(other)
        return NotImplemented

    def __hash__(self):
        return hash(self._raw)

    def __str__(self):
        r = self._raw
        return "urn:smpte:umid:" + ".".join(
            r[i:i + 4].hex() for i in range(0, 32, 4))

    def __repr__(self):
        return "<MobID %s>" % self.hex()

    def hex(self) -> str:
        return self._raw.hex()
