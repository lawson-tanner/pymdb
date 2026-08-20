"""The reader you actually use: :class:`MDBFile`.

    >>> import mdb
    >>> with mdb.open("msmMMOB.mdb") as f:
    ...     for mob in f.mobs:
    ...         print(mob.name, mob.paths())

Objects are built lazily and cached, so opening a 3 MB database costs only the
container parse; walking a handful of mobs never touches the other 17,000
objects.
"""
from __future__ import annotations

import io
import os
from collections import Counter, defaultdict
from typing import (Any, Dict, Iterable, Iterator, List, Optional, Sequence, Union)

from .bento import BentoContainer, NotABentoContainer, TOCEntry, std
from .core import CLASS_REGISTRY, MDBObject, class_for
from .mobid import MobID, ShortUID
from .objects import (Attribute, AttributeList, BinLink, ClassDescriptor, Header,
                      Locator, MediaDescriptor, MediaStreamLink, Mob,
                      MobReference, SourceClip)

__all__ = ["MDBFile", "open_mdb"]


class MDBFile(object):
    """An open Avid media database.

    The class-based indexes (:attr:`mobs`, :meth:`by_class`) and the MobID
    index are built on first use, because the common troubleshooting question
    ("where did this clip's media go?") only needs a few of them.
    """

    def __init__(self, fileobject: Union[str, os.PathLike, io.IOBase, bytes],
                 path: Optional[str] = None):
        if isinstance(fileobject, (bytes, bytearray)):
            self.container = BentoContainer(bytes(fileobject), path=path)
        else:
            self.container = BentoContainer.from_file(fileobject)
        self.path = self.container.path
        self._objects: Dict[int, MDBObject] = {}
        self._class_index: Optional[Dict[str, List[int]]] = None
        self._mobid_index: Optional[Dict[bytes, List[int]]] = None
        self._material_index: Optional[Dict[bytes, List[int]]] = None
        self._referrer_index: Optional[Dict[int, List[int]]] = None
        self._class_map: Dict[str, type] = {}
        self._declared_parents: Optional[Dict[str, Optional[str]]] = None

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        """Drop the file image and every cached object."""
        self._objects.clear()
        self._class_index = None
        self._mobid_index = None
        self._material_index = None
        self._referrer_index = None
        self._class_map.clear()
        self._declared_parents = None

    def __enter__(self) -> "MDBFile":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- objects -----------------------------------------------------------
    def object(self, object_id: int) -> Optional[MDBObject]:
        """The object with this ID, or ``None`` if the file has no such object."""
        cached = self._objects.get(object_id)
        if cached is not None:
            return cached
        entries = self.container.objects.get(object_id)
        if entries is None:
            return None
        obj = self.class_for_id(self._class_id_of(entries))(self, object_id, entries)
        self._objects[object_id] = obj
        return obj

    def __getitem__(self, object_id: int) -> MDBObject:
        obj = self.object(object_id)
        if obj is None:
            raise KeyError("no object 0x%x in this file" % object_id)
        return obj

    def class_for_id(self, class_id: Optional[str]) -> type:
        """The Python class to build for a 4CC, consulting the file itself.

        A 4CC the library knows resolves straight from the registry.  One it
        does not is looked up in *this file's* ``HEAD.ClassDictionary``, and
        the nearest declared ancestor that the library does know is used
        instead -- so an unrecognised ``CDCI`` subclass still reads as a
        picture descriptor rather than as a bare :class:`~mdb.core.MDBObject`,
        with its own properties still reachable by OMF name.

        This is the whole reason the class dictionary is in the file: Media
        Composer writes the inheritance so that a reader which has never heard
        of a class can still place it.  Falling back to ``MDBObject`` when the
        file has told us the answer would be throwing that away.
        """
        if not class_id:
            return MDBObject
        cached = self._class_map.get(class_id)
        if cached is not None:
            return cached
        known = class_for(class_id)
        if known is not MDBObject or class_id == "":
            self._class_map[class_id] = known
            return known
        # a 4CC that differs only in case is Avid's own typo, not a new
        # class: the dictionary of both reference samples declares both
        # 'ASPI' and 'ASpi'.  Prefer the cased match over walking parents.
        for known_id, cls in CLASS_REGISTRY.items():
            if known_id.lower() == class_id.lower():
                self._class_map[class_id] = cls
                return cls
        found = MDBObject
        seen = {class_id}
        parent = self._class_parents().get(class_id)
        while parent and parent not in seen:
            seen.add(parent)
            candidate = class_for(parent)
            if candidate is not MDBObject:
                found = candidate
                break
            parent = self._class_parents().get(parent)
        self._class_map[class_id] = found
        return found

    def _class_parents(self) -> Dict[str, Optional[str]]:
        """``{4CC: parent 4CC}`` as this file's class dictionary declares it.

        Built once.  ``CLSD`` and ``HEAD`` are both in the static registry, so
        reading the dictionary never needs the dictionary -- but the map is
        installed empty first anyway, so a damaged file that somehow made the
        lookup re-entrant terminates instead of recursing.
        """
        if self._declared_parents is not None:
            return self._declared_parents
        self._declared_parents = {}
        parents: Dict[str, Optional[str]] = {}
        try:
            for entry in self.class_dictionary:
                four_cc = entry.class_4cc
                if four_cc:
                    parents[four_cc] = entry.parent_4cc
        except Exception:
            # a class dictionary we cannot read is a reason to fall back to
            # MDBObject, never a reason to fail opening the file
            parents = {}
        self._declared_parents = parents
        return parents

    def _class_id_of(self, entries: Sequence[TOCEntry]) -> Optional[str]:
        container = self.container
        found = None
        for e in entries:
            if container.name_of(e.property_id) == "OMFI:ObjID":
                found = container.entry_bytes(e).rstrip(b"\0").decode("latin-1")
        return found

    def class_of(self, object_id: int) -> Optional[str]:
        """The 4CC of an object, without building the object."""
        entries = self.container.objects.get(object_id)
        return self._class_id_of(entries) if entries else None

    def objects(self, data_only: bool = True) -> Iterator[MDBObject]:
        """Every object, in TOC order.  Schema-registry objects are skipped by default."""
        for oid in self.container.objects:
            if data_only and self.container.is_schema(oid):
                continue
            obj = self.object(oid)
            if obj is not None:
                yield obj

    # -- the header --------------------------------------------------------
    @property
    def header(self) -> Header:
        """The OMFi ``HEAD``, which shares object 1 with Bento's container object."""
        return self[std.CONTAINER_OBJECT]

    @property
    def last_modified(self):
        return self.header.last_modified

    # -- class index -------------------------------------------------------
    def _build_class_index(self) -> Dict[str, List[int]]:
        if self._class_index is None:
            index: Dict[str, List[int]] = defaultdict(list)
            for oid, entries in self.container.objects.items():
                cid = self._class_id_of(entries)
                if cid:
                    index[cid].append(oid)
            self._class_index = dict(index)
        return self._class_index

    def by_class(self, class_id: str) -> List[MDBObject]:
        """Every object of one 4CC, e.g. ``f.by_class('MSML')``."""
        return [self[oid] for oid in self._build_class_index().get(class_id, ())]

    def class_census(self) -> "Counter[str]":
        """``{4CC: count}`` -- the fastest way to see what a file contains."""
        return Counter({k: len(v) for k, v in self._build_class_index().items()})

    @property
    def mobs(self) -> List[Mob]:
        """Every ``MOBJ`` object in the file, in TOC order.

        This includes deleted mobs -- see :meth:`deleted_mobs`.  For the list
        Media Composer itself considers live, use :attr:`spine_mobs`.
        """
        return [m for m in self.by_class("MOBJ") if isinstance(m, Mob)]

    @property
    def spine_mobs(self) -> List[Mob]:
        """The live mobs, as listed by ``HEAD.ObjectSpine``."""
        return self.header.mobs()

    def deleted_mobs(self) -> List[Mob]:
        """Mobs present in the container but dropped from ``HEAD.ObjectSpine``.

        Deleting a mob unlinks it from the spine and from every other object,
        but leaves its TOC entries and heap values in place.  In both reference
        samples the count of these orphans equals ``HEAD.NumDelMobs`` exactly,
        and each orphan duplicates the MobID of a live mob -- so a MobID is
        *not* unique across MOBJ objects, only across live ones.
        """
        live = {m.object_id for m in self.spine_mobs}
        return [m for m in self.mobs if m.object_id not in live]

    def mobs_by_id(self, mob_id: Union[MobID, bytes, str]) -> List[Mob]:
        """Every mob carrying this MobID -- normally one, two if one is deleted."""
        self._build_mobid_index()
        if isinstance(mob_id, str):
            mob_id = MobID.from_hex(mob_id)
        key = mob_id.bytes if isinstance(mob_id, MobID) else bytes(mob_id)
        return [self[oid] for oid in self._mobid_index.get(key, ())]

    @property
    def locators(self) -> List[Locator]:
        return [o for o in self.objects() if isinstance(o, Locator)]

    @property
    def descriptors(self) -> List[MediaDescriptor]:
        return [o for o in self.objects() if isinstance(o, MediaDescriptor)]

    @property
    def class_dictionary(self) -> List[ClassDescriptor]:
        """HEAD's metadict: Avid's extension classes and their inheritance."""
        return [c for c in (self.header.class_dictionary or [])
                if isinstance(c, ClassDescriptor)]

    # -- MobID index -------------------------------------------------------
    def _build_mobid_index(self):
        if self._mobid_index is not None:
            return
        by_id: Dict[bytes, List[int]] = defaultdict(list)
        by_material: Dict[bytes, List[int]] = defaultdict(list)
        for oid, entries in self.container.objects.items():
            if self._class_id_of(entries) != "MOBJ":
                continue
            mob_id = self[oid].get("OMFI:MOBJ:MobID")
            if isinstance(mob_id, MobID):
                if oid not in by_id[mob_id.bytes]:
                    by_id[mob_id.bytes].append(oid)
                if oid not in by_material[mob_id.material]:
                    by_material[mob_id.material].append(oid)
        self._mobid_index = dict(by_id)
        self._material_index = dict(by_material)

    def mob_by_id(self, mob_id: Union[MobID, bytes, str]) -> Optional[Mob]:
        """Find a mob by full 32-byte UMID."""
        self._build_mobid_index()
        if isinstance(mob_id, str):
            mob_id = MobID.from_hex(mob_id)
        key = mob_id.bytes if isinstance(mob_id, MobID) else bytes(mob_id)
        return self._prefer_live(self._mobid_index.get(key))

    def mob_by_short_uid(self, uid: Union[ShortUID, bytes]) -> Optional[Mob]:
        """Find a mob by OMF1 short UID -- how ``SCLP:SourceID`` names its source."""
        self._build_mobid_index()
        material = uid.material if isinstance(uid, ShortUID) else bytes(uid)[4:12]
        found = self._prefer_live(self._material_index.get(material))
        if found is not None:
            return found
        # fall back to HEAD's own index, which is what Media Composer consults
        for entry in self.mob_index_entries():
            if entry.uid.material == material:
                obj = self.object(entry.object_id)
                if isinstance(obj, Mob):
                    return obj
        return None

    def _prefer_live(self, object_ids) -> Optional[Mob]:
        """Pick a live mob over a deleted twin when a MobID names both."""
        if not object_ids:
            return None
        if len(object_ids) > 1:
            live = {m.object_id for m in self.spine_mobs}
            for oid in object_ids:
                if oid in live:
                    return self[oid]
        return self[object_ids[0]]

    def mob_index_entries(self):
        """HEAD's ``SourceMobs`` and ``CompositionMobs`` fast-lookup records."""
        head = self.header
        return list(head.get("OMFI:SourceMobs") or []) + \
               list(head.get("OMFI:CompositionMobs") or [])

    def links_for(self, mob_id: Union[MobID, bytes, None]) -> List[MDBObject]:
        """MSML / MCBR / MCMR objects carrying this MobID.

        These link by MobID *value*, not by object reference, so this is a
        value scan rather than a pointer walk.
        """
        if mob_id is None:
            return []
        key = mob_id.bytes if isinstance(mob_id, MobID) else bytes(mob_id)
        out: List[MDBObject] = []
        # MCBR is absent by design: it carries a bin name and ID but no MobID,
        # and is reached through the attribute tree instead (see Mob.bin_links).
        for class_id, prop in (("MSML", "OMFI:MSML:MobID"),
                               ("MCMR", "OMFI:MCMR:MC:MobID")):
            for obj in self.by_class(class_id):
                value = obj.get(prop)
                if isinstance(value, MobID) and value.bytes == key:
                    out.append(obj)
        return out

    # -- searching ---------------------------------------------------------
    def find_bytes(self, needle: Union[bytes, str], limit: int = 100):
        """Locate raw bytes in the value heap and report which entry owns them.

        Yields ``(offset, entry)`` pairs.  Matches inside the TOC or label are
        skipped -- only heap values are meaningful.
        """
        if isinstance(needle, str):
            needle = needle.encode("utf-8")
        data = self.container.data
        heap_end = self.container.label.toc_offset
        pos, found = 0, 0
        while found < limit:
            pos = data.find(needle, pos)
            if pos < 0 or pos >= heap_end:
                return
            for entry in self.container.owners(pos):
                yield pos, entry
            found += 1
            pos += 1

    def find(self, text: str, limit: int = 100) -> List[MDBObject]:
        """Objects whose values contain ``text``, deduplicated, in file order."""
        seen, out = set(), []
        for _offset, entry in self.find_bytes(text, limit=limit):
            if entry.object_id in seen:
                continue
            seen.add(entry.object_id)
            obj = self.object(entry.object_id)
            if obj is not None:
                out.append(obj)
        return out

    def owner_of(self, offset: int) -> List[MDBObject]:
        """Which object wrote the byte at ``offset`` -- for corruption triage."""
        seen, out = set(), []
        for entry in self.container.owners(offset):
            if entry.object_id in seen:
                continue
            seen.add(entry.object_id)
            obj = self.object(entry.object_id)
            if obj is not None:
                out.append(obj)
        return out

    def mobs_on_volume(self, volume: str) -> List[Mob]:
        """Every mob whose MSML link names ``volume`` (case-insensitive substring)."""
        needle = volume.lower()
        out = []
        for link in self.by_class("MSML"):
            if not isinstance(link, MediaStreamLink):
                continue
            vol = link.volume or ""
            if needle in vol.lower():
                mob = self.mob_by_id(link.mob_id) if link.mob_id else None
                if mob is not None and mob not in out:
                    out.append(mob)
        return out

    def mobs_in_bin(self, bin_name: str) -> List[Mob]:
        """Mobs whose ``_ORG_BIN`` attribute names a matching ``.avb`` bin.

        MCBR carries no MobID, so this walks the attribute tree rather than
        matching by value (case-insensitive substring).
        """
        needle = bin_name.lower()
        return [m for m in self.mobs
                if any(needle in name.lower() for name in m.bins())]

    def referrers(self, object_id: int) -> List[MDBObject]:
        """Objects that hold a reference to ``object_id``.

        The reverse index is built once, on first use: the format stores only
        forward references, so answering "what points at this?" otherwise means
        a full scan every time.
        """
        if self._referrer_index is None:
            index: Dict[int, List[int]] = defaultdict(list)
            for oid in self.container.objects:
                obj = self.object(oid)
                if obj is None:
                    continue
                for ref in obj.referenced_ids():
                    if oid not in index[ref]:
                        index[ref].append(oid)
            self._referrer_index = dict(index)
        return [self[oid] for oid in self._referrer_index.get(object_id, ())]

    # -- reporting ---------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        lab = self.container.label
        head = self.header
        return {
            "path": self.path,
            "size": self.container.size,
            "bento_version": "%d.%d" % (lab.major, lab.minor),
            "byte_order": lab.byte_order.decode("ascii"),
            "toc_offset": lab.toc_offset,
            "toc_size": lab.toc_size,
            "entries": len(self.container.entries),
            "objects": len(self.container.objects),
            "minseed": self.container.minseed,
            "seed": self.container.seed,
            "schema_names": len(self.container.names),
            "first_data_entry": self.container.first_data_entry_index,
            "last_modified": head.last_modified,
            "mobs": len(self._build_class_index().get("MOBJ", ())),
            "classes": dict(self.class_census().most_common()),
        }

    def __repr__(self):
        return "<MDBFile %s %d objects>" % (
            os.path.basename(self.path) if self.path else "<bytes>",
            len(self.container.objects))


def _reachable_ids(obj: MDBObject, depth: int = 3, _seen=None) -> Iterable[int]:
    """Object IDs reachable from ``obj`` within ``depth`` reference hops."""
    if _seen is None:
        _seen = set()
    if depth < 0 or obj.object_id in _seen:
        return _seen
    _seen.add(obj.object_id)
    root = obj.root
    for oid in obj.referenced_ids():
        child = root.object(oid)
        if child is not None:
            _reachable_ids(child, depth - 1, _seen)
        else:
            _seen.add(oid)
    return _seen


def open_mdb(fileobject, path: Optional[str] = None) -> MDBFile:
    """Open an Avid ``msmMMOB.mdb``.  Exposed as :func:`mdb.open`."""
    return MDBFile(fileobject, path=path)
