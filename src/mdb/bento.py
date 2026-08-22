"""Layer 0 -- the Bento container.

An Avid ``msmMMOB.mdb`` is a Bento container (Bento Specification 1.0d5,
Harris & Ruben, Apple 1993), the same container OMF Interchange is built on.
It has no header: the only correct entry point is the **last 24 bytes**.

.. code-block:: text

    offset 0  +---------------------------------------------+
              | VALUE HEAP  (out-of-line property values)    |
              +---------------------------------------------+
              | TOC         (N x 24-byte entries)            |
    EOF-24    +---------------------------------------------+
              | CONTAINER LABEL (24 bytes)                   |
    EOF       +---------------------------------------------+

This module knows nothing about OMF or Avid.  It gives you the label, the
TOC, objects-as-groups-of-entries, and the schema registry that turns numeric
property/type IDs into names.
"""
from __future__ import annotations

import io
import os
import struct
from collections import OrderedDict, defaultdict
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

__all__ = [
    "MAGIC", "LABEL_SIZE", "ENTRY_SIZE", "IMMEDIATE",
    "BentoError", "NotABentoContainer", "CorruptContainer",
    "ContainerLabel", "TOCEntry", "BentoContainer", "std",
]

MAGIC = bytes.fromhex("a4434da5486472d7")   # "\xa4CM\xa5Hdr\xd7"
LABEL_SIZE = 24
ENTRY_SIZE = 24

#: high half of ``gen_flags``; set means the value lives inside the TOC entry
IMMEDIATE = 0x0001 << 16

LITTLE = b"II"
BIG = b"MM"


# --------------------------------------------------------------------------
# Bento standard IDs (0x01-0x1F).  Roles verified behaviourally against the
# reference samples; authoritative names live in the Bento 1.0d5 spec.
# --------------------------------------------------------------------------
class std:
    """Bento standard object / property / type IDs."""

    CONTAINER_OBJECT = 0x01     # object 1: the container object (OMF overlays HEAD on it)

    P_SEED = 0x02               # next objectID to allocate
    P_MINSEED = 0x03            # first data-object ID
    P_TOC_OBJECT = 0x04         # the TOC itself: (offset, size)
    P_CONTAINER = 0x05          # the whole container: (0, filesize)
    P_DELETED = 0x06
    P_SPACE_DELETED = 0x07
    P_0xF = 0x0F
    P_OBJ_NAME = 0x16           # binds a name to an object ID
    P_TYPE_NAME = 0x17          # binds a name to a type ID
    P_PROP_NAME = 0x18          # binds a name to a property ID

    T_OFFSET_LENGTH = 0x13      # value is the entry's own (value, length) pair
    T_GLOBAL_NAME = 0x15        # NUL-terminated name string

    #: properties whose "value" field is an offset that is *not* a heap
    #: allocation (they describe the file's own geometry)
    GEOMETRY_PROPERTIES = frozenset({P_TOC_OBJECT, P_CONTAINER})

    NAME_PROPERTIES = frozenset({P_OBJ_NAME, P_TYPE_NAME, P_PROP_NAME})

    NAMES = {
        CONTAINER_OBJECT: "<std:container-object>",
        P_SEED: "<std:seed>",
        P_MINSEED: "<std:minseed>",
        P_TOC_OBJECT: "<std:TOC>",
        P_CONTAINER: "<std:container>",
        P_DELETED: "<std:deleted>",
        P_SPACE_DELETED: "<std:spaceDeleted>",
        P_0xF: "<std:0xF>",
        P_OBJ_NAME: "<std:objectName>",
        P_TYPE_NAME: "<std:typeName>",
        P_PROP_NAME: "<std:propertyName>",
        T_OFFSET_LENGTH: "<std:offset/length>",
        T_GLOBAL_NAME: "<std:globalName>",
    }


class BentoError(Exception):
    """Base class for container-level errors."""


class NotABentoContainer(BentoError):
    """The file has no Bento container label at EOF."""


class CorruptContainer(BentoError):
    """The label or TOC is self-inconsistent."""


# --------------------------------------------------------------------------
# Container label
# --------------------------------------------------------------------------
class ContainerLabel(object):
    """The 24 bytes at ``EOF - 24``.  The only self-describing part of the file."""

    __slots__ = ("flags", "byte_order", "major", "minor", "toc_offset", "toc_size")

    def __init__(self, flags, byte_order, major, minor, toc_offset, toc_size):
        self.flags = flags
        self.byte_order = byte_order
        self.major = major
        self.minor = minor
        self.toc_offset = toc_offset
        self.toc_size = toc_size

    @classmethod
    def unpack(cls, raw: bytes) -> "ContainerLabel":
        if len(raw) != LABEL_SIZE:
            raise CorruptContainer("label must be %d bytes, got %d" % (LABEL_SIZE, len(raw)))
        if raw[:8] != MAGIC:
            raise NotABentoContainer(
                "no Bento container label at EOF (magic %s != %s)"
                % (raw[:8].hex(), MAGIC.hex()))
        byte_order = raw[10:12]
        if byte_order not in (LITTLE, BIG):
            raise CorruptContainer("unknown byte-order marker %r" % (byte_order,))
        end = "<" if byte_order == LITTLE else ">"
        flags, = struct.unpack(end + "H", raw[8:10])
        major, minor, toc_offset, toc_size = struct.unpack(end + "HHII", raw[12:24])
        return cls(flags, byte_order, major, minor, toc_offset, toc_size)

    @property
    def endian(self) -> str:
        """``'<'`` or ``'>'``, ready for :mod:`struct`."""
        return "<" if self.byte_order == LITTLE else ">"

    @property
    def little_endian(self) -> bool:
        return self.byte_order == LITTLE

    @property
    def entry_count(self) -> int:
        return self.toc_size // ENTRY_SIZE

    def __repr__(self):
        return ("<ContainerLabel %d.%d %s toc@0x%x size=0x%x (%d entries)>"
                % (self.major, self.minor, self.byte_order.decode("ascii"),
                   self.toc_offset, self.toc_size, self.entry_count))


# --------------------------------------------------------------------------
# TOC entry
# --------------------------------------------------------------------------
class TOCEntry(object):
    """One 24-byte TOC record: ``(object, property, type, value, length, gen/flags)``.

    Entries are the whole database.  An *object* has no physical record of its
    own -- it is simply the set of entries sharing an ``object_id``.
    """

    __slots__ = ("object_id", "property_id", "type_id", "value", "length",
                 "gen_flags", "index")

    def __init__(self, object_id, property_id, type_id, value, length, gen_flags, index=-1):
        self.object_id = object_id
        self.property_id = property_id
        self.type_id = type_id
        self.value = value
        self.length = length
        self.gen_flags = gen_flags
        self.index = index

    @property
    def immediate(self) -> bool:
        """True when the value is stored inside the entry rather than the heap."""
        return bool(self.gen_flags & IMMEDIATE)

    @property
    def generation(self) -> int:
        return self.gen_flags & 0xFFFF

    @property
    def flags(self) -> int:
        return (self.gen_flags >> 16) & 0xFFFF

    @property
    def offset(self) -> Optional[int]:
        """Heap offset of the value, or ``None`` for immediates."""
        return None if self.immediate else self.value

    def __repr__(self):
        where = "imm" if self.immediate else ("@0x%x" % self.value)
        return ("<TOCEntry #%d obj=0x%x prop=0x%x type=0x%x %s len=%d>"
                % (self.index, self.object_id, self.property_id,
                   self.type_id, where, self.length))


# --------------------------------------------------------------------------
# The container
# --------------------------------------------------------------------------
class BentoContainer(object):
    """A parsed Bento container: label, TOC, objects, schema names.

    Nothing here is OMF- or Avid-specific.  The whole file is read into memory;
    MDBs are index files (tens of KB to a few MB), so this is the right trade.
    """

    def __init__(self, data: bytes, path: Optional[str] = None):
        self.data = data
        self.path = path
        self.size = len(data)

        if self.size < LABEL_SIZE:
            raise NotABentoContainer("file is only %d bytes" % self.size)

        self.label = ContainerLabel.unpack(data[-LABEL_SIZE:])
        self._endian = self.label.endian
        self._validate_geometry()
        self.entries = self._read_toc()

        #: object_id -> list of entries, in TOC order
        self.objects: Dict[int, List[TOCEntry]] = OrderedDict()
        for e in self.entries:
            self.objects.setdefault(e.object_id, []).append(e)

        self._read_schema()
        self.minseed = self._read_container_int(std.P_MINSEED, default=0x109A0)
        self.seed = self._read_container_int(std.P_SEED, default=0)

    # -- construction ------------------------------------------------------
    @classmethod
    def from_file(cls, fileobject) -> "BentoContainer":
        """Open a path, path-like, or binary file object."""
        if hasattr(fileobject, "read"):
            pos = fileobject.tell() if hasattr(fileobject, "tell") else None
            data = fileobject.read()
            if pos is not None:
                try:
                    fileobject.seek(pos)
                except (OSError, io.UnsupportedOperation):
                    pass
            name = getattr(fileobject, "name", None)
            return cls(data, path=name if isinstance(name, str) else None)
        path = os.fspath(fileobject)
        with io.open(path, "rb") as f:
            return cls(f.read(), path=path)

    def _validate_geometry(self):
        lab = self.label
        if lab.toc_size % ENTRY_SIZE:
            raise CorruptContainer(
                "TOC size 0x%x is not a multiple of %d" % (lab.toc_size, ENTRY_SIZE))
        if lab.toc_offset + lab.toc_size + LABEL_SIZE != self.size:
            raise CorruptContainer(
                "TOC geometry does not reach the label: 0x%x + 0x%x + %d != 0x%x"
                % (lab.toc_offset, lab.toc_size, LABEL_SIZE, self.size))

    def _read_toc(self) -> List[TOCEntry]:
        lab = self.label
        raw = self.data[lab.toc_offset:lab.toc_offset + lab.toc_size]
        fmt = self._endian + "6I"
        unpack = struct.Struct(fmt).unpack_from
        return [TOCEntry(*unpack(raw, i * ENTRY_SIZE), index=i)
                for i in range(lab.entry_count)]

    def _read_schema(self):
        """Resolve the name registry -- properties 0x16/0x17/0x18 bind names to IDs.

        A handful of schema objects in real files bind *two different* names to
        one numeric ID, so every binding is kept; :attr:`names` exposes the last
        (which is what Media Composer itself appears to use) and
        :attr:`all_names` keeps the full list for diagnostics.
        """
        all_names: Dict[int, List[str]] = defaultdict(list)
        for e in self.entries:
            if e.property_id in std.NAME_PROPERTIES:
                raw = self.entry_bytes(e)
                all_names[e.object_id].append(raw.split(b"\0", 1)[0].decode("latin-1"))
        self.all_names: Dict[int, List[str]] = dict(all_names)
        self.names: Dict[int, str] = {k: v[-1] for k, v in all_names.items()}

    def _read_container_int(self, property_id: int, default: int = 0) -> int:
        for e in self.objects.get(std.CONTAINER_OBJECT, ()):
            if e.property_id == property_id:
                return e.value
        return default

    # -- values ------------------------------------------------------------
    def entry_bytes(self, entry: TOCEntry) -> bytes:
        """Raw bytes of an entry's value.

        Immediates are unpacked from the entry itself (left-justified, ``length``
        of the 4 bytes).  Geometry properties (the TOC object, the container)
        describe file regions rather than heap allocations and return ``b''``.
        """
        if entry.immediate:
            return struct.pack(self._endian + "I", entry.value)[:entry.length]
        if entry.property_id in std.GEOMETRY_PROPERTIES:
            return b""
        start = entry.value
        end = start + entry.length
        if end > self.size:
            raise CorruptContainer(
                "value of %r runs past EOF (0x%x > 0x%x)" % (entry, end, self.size))
        return self.data[start:end]

    # -- naming ------------------------------------------------------------
    def name_of(self, ident: int) -> str:
        """Human-readable name for an object / property / type ID."""
        name = self.names.get(ident)
        if name is not None:
            return name
        name = std.NAMES.get(ident)
        if name is not None:
            return name
        return "0x%x" % ident

    def is_schema(self, object_id: int) -> bool:
        return object_id < self.minseed and object_id != std.CONTAINER_OBJECT

    def is_data(self, object_id: int) -> bool:
        return object_id >= self.minseed

    # -- iteration ---------------------------------------------------------
    def data_object_ids(self) -> Iterator[int]:
        """Object IDs of real content objects (>= minseed), in TOC order."""
        for oid in self.objects:
            if oid >= self.minseed:
                yield oid

    def entries_for(self, object_id: int) -> List[TOCEntry]:
        return self.objects.get(object_id, [])

    def find_property(self, object_id: int, property_name: str) -> List[TOCEntry]:
        """All entries of ``object_id`` whose property resolves to ``property_name``."""
        return [e for e in self.objects.get(object_id, ())
                if self.name_of(e.property_id) == property_name]

    @property
    def first_data_entry_index(self) -> Optional[int]:
        for e in self.entries:
            if e.object_id >= self.minseed:
                return e.index
        return None

    def owners(self, offset: int) -> List[TOCEntry]:
        """Every entry whose heap value covers ``offset`` -- unique in a healthy file.

        The workhorse for corruption triage and for answering "who owns byte X?".
        """
        return [e for e in self.entries
                if not e.immediate and e.length > 0
                and e.property_id not in std.GEOMETRY_PROPERTIES
                and e.value <= offset < e.value + e.length]

    def __len__(self):
        return len(self.objects)

    def __repr__(self):
        return ("<BentoContainer %s %d entries / %d objects, minseed=0x%x>"
                % (os.path.basename(self.path) if self.path else "<bytes>",
                   len(self.entries), len(self.objects), self.minseed))
