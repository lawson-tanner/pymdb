"""Layer 1 base -- objects with names.

Layer 0 (:mod:`mdb.bento`) hands back entries keyed by number.  This layer
gives each object a Python class chosen by its ``OMFI:ObjID`` 4CC, decodes
values on demand, and resolves object references into live objects.

Two rules shape the design, both learned from the format itself:

*Unknown classes must still parse.*  An unrecognised 4CC becomes a
:class:`MDBObject` with every property readable by its OMF name.  Media
Composer adds classes; a reader that raises on them is a reader that breaks
on next year's files.

*Properties can repeat.*  ``MOBJ:MobID`` is written twice with identical
content, a WINL can carry two different ``FL:PathNameUTF8`` values, and
``DIDD:VideoLineMap`` genuinely is a multi-value property.  Attribute access
gives you the last value (what Media Composer appears to use); :meth:`values`
gives you all of them.
"""
from __future__ import annotations

import weakref
from typing import (Any, Dict, Iterator, List, Optional, Sequence, Tuple, TYPE_CHECKING)

from . import datatypes
from .bento import TOCEntry, std

if TYPE_CHECKING:  # pragma: no cover
    from .file import MDBFile

__all__ = ["PropertyDef", "MDBObject", "register_class", "class_for",
           "CLASS_REGISTRY", "UnresolvedRef"]

_sentinel = object()


class UnresolvedRef(object):
    """An object reference that does not resolve -- kept rather than dropped."""

    __slots__ = ("object_id",)

    def __init__(self, object_id: int):
        self.object_id = object_id

    def __eq__(self, other):
        return isinstance(other, UnresolvedRef) and other.object_id == self.object_id

    def __hash__(self):
        return hash(("unresolved", self.object_id))

    def __repr__(self):
        return "<UnresolvedRef 0x%x>" % self.object_id


class PropertyDef(object):
    """Binds a Python attribute name to an OMF property name.

    ``deref`` turns ``omfi:ObjRef`` / ``omfi:ObjRefArray`` values into objects.
    ``enum`` names a table in :mod:`mdb.enums` so ``obj.track_kind_name`` works
    alongside the raw ``obj.track_kind``.
    """

    __slots__ = ("name", "omf_name", "deref", "enum", "doc", "multi")

    def __init__(self, name: str, omf_name: str, deref: bool = False,
                 enum: Optional[Dict[int, str]] = None, doc: str = "",
                 multi: bool = False):
        self.name = name
        self.omf_name = omf_name
        self.deref = deref
        self.enum = enum
        self.doc = doc
        self.multi = multi

    def __repr__(self):
        return "<PropertyDef %s -> %s>" % (self.name, self.omf_name)


CLASS_REGISTRY: Dict[str, type] = {}


def register_class(cls: type) -> type:
    """Class decorator: bind a Python class to its OMF 4CC."""
    if cls.class_id:
        CLASS_REGISTRY[cls.class_id] = cls
    return cls


def class_for(class_id: Optional[str]) -> type:
    return CLASS_REGISTRY.get(class_id or "", MDBObject)


class _PropertyMeta(type):
    """Collects ``propertydefs`` down the inheritance chain.

    OMF's class hierarchy is real -- a MOBJ carries CPNT, TRKG and MOBJ
    properties -- so subclasses inherit their parents' definitions and the
    lookup table is built once per class rather than per instance.
    """

    def __init__(cls, name, bases, ns):
        super().__init__(name, bases, ns)
        merged: "Dict[str, PropertyDef]" = {}
        for base in reversed(cls.__mro__[1:]):
            merged.update(getattr(base, "_propertydefs_by_name", {}) or {})
        for pdef in ns.get("propertydefs", ()):
            merged[pdef.name] = pdef
        cls._propertydefs_by_name = merged
        cls._propertydefs_by_omf = {p.omf_name: p for p in merged.values()}

        structural: "Dict[str, None]" = {}
        for base in reversed(cls.__mro__[1:]):
            structural.update(dict.fromkeys(getattr(base, "_structural_properties", ())))
        structural.update(dict.fromkeys(ns.get("structural_properties", ())))
        cls._structural_properties = tuple(structural)


class MDBObject(metaclass=_PropertyMeta):
    """One object: a set of TOC entries sharing an object ID.

    Access properties three ways, in increasing order of rawness::

        mob.name                        # typed attribute, per propertydefs
        mob["OMFI:CPNT:Name"]           # by OMF property name
        mob.values("OMFI:MOBJ:MobID")   # every value, duplicates included
    """

    #: OMF 4CC; ``None`` on abstract bases
    class_id: Optional[str] = None
    propertydefs: Sequence[PropertyDef] = ()

    #: OMF property names this class reads *structurally* rather than through
    #: a :class:`PropertyDef` -- the parallel per-point, per-band and
    #: per-keyframe columns, and the numerator/denominator pairs that make up
    #: a rectangle.  They have no single sensible attribute name (there are
    #: *n* of each), so a method assembles them instead; listing them here
    #: keeps them visible to :meth:`known_properties` and to the coverage
    #: tests, so a property cannot be quietly forgotten.
    structural_properties: Sequence[str] = ()

    __slots__ = ("object_id", "_rootref", "_entries", "_cache", "__weakref__")

    def __init__(self, root: "MDBFile", object_id: int, entries: List[TOCEntry]):
        self.object_id = object_id
        self._rootref = weakref.ref(root)
        self._entries = entries
        self._cache: Dict[str, Any] = {}

    # -- plumbing ----------------------------------------------------------
    @property
    def root(self) -> "MDBFile":
        root = self._rootref()
        if root is None:
            raise ReferenceError("the MDBFile that owns this object has been closed")
        return root

    @property
    def entries(self) -> List[TOCEntry]:
        """The raw TOC entries backing this object, in file order."""
        return self._entries

    @property
    def class_name(self) -> str:
        """The 4CC actually found in the file, which may not match :attr:`class_id`."""
        v = self._raw_values("OMFI:ObjID")
        return v[-1] if v else ""

    # -- reading -----------------------------------------------------------
    def _raw_values(self, omf_name: str) -> List[Any]:
        container = self.root.container
        endian = container.label.endian
        out = []
        for e in self._entries:
            if container.name_of(e.property_id) != omf_name:
                continue
            if e.property_id in std.GEOMETRY_PROPERTIES:
                out.append(datatypes.OffsetLength(e.value, e.length))
                continue
            type_name = container.name_of(e.type_id)
            out.append(datatypes.decode(type_name, container.entry_bytes(e),
                                        endian, property_name=omf_name))
        return out

    def values(self, omf_name: str) -> List[Any]:
        """Every value written for ``omf_name``, in file order.

        Duplicates are normal in this format; this is how you see them.
        """
        key = "*" + omf_name
        cached = self._cache.get(key, _sentinel)
        if cached is _sentinel:
            cached = self._raw_values(omf_name)
            self._cache[key] = cached
        return cached

    def get(self, omf_name: str, default: Any = None, deref: bool = False) -> Any:
        """The last value written for ``omf_name``, or ``default``."""
        vals = self.values(omf_name)
        if not vals:
            return default
        value = vals[-1]
        return self._deref(value) if deref else value

    def __getitem__(self, omf_name: str) -> Any:
        vals = self.values(omf_name)
        if not vals:
            raise KeyError(omf_name)
        return vals[-1]

    def __contains__(self, omf_name: str) -> bool:
        return bool(self.values(omf_name))

    def _deref(self, value: Any) -> Any:
        root = self.root

        def one(v):
            # NB: never use `or` here -- an empty ATTR or SEQU is falsy, and a
            # legitimate object would be misreported as unresolved.
            if not isinstance(v, int):
                return v
            obj = root.object(v)
            return UnresolvedRef(v) if obj is None else obj

        if isinstance(value, list):
            return [one(v) for v in value]
        return one(value)

    # -- typed attribute access -------------------------------------------
    def __getattr__(self, name: str) -> Any:
        # only reached when normal lookup fails, so __slots__ still apply
        if name.startswith("_"):
            raise AttributeError(name)

        pdef = self._propertydefs_by_name.get(name)
        if pdef is None and name.endswith("_name"):
            base = self._propertydefs_by_name.get(name[:-5])
            if base is not None and base.enum is not None:
                from .enums import label
                return label(base.enum, self.get(base.omf_name), base.name)
        if pdef is None:
            raise AttributeError("%s has no property %r"
                                 % (type(self).__name__, name))

        cached = self._cache.get(name, _sentinel)
        if cached is not _sentinel:
            return cached

        if pdef.multi:
            value = self.values(pdef.omf_name)
            if pdef.deref:
                value = [self._deref(v) for v in value]
        else:
            value = self.get(pdef.omf_name, None, deref=pdef.deref)
        self._cache[name] = value
        return value

    # -- introspection -----------------------------------------------------
    def property_names(self) -> List[str]:
        """OMF names of every property present, in file order, deduplicated."""
        container = self.root.container
        seen, out = set(), []
        for e in self._entries:
            n = container.name_of(e.property_id)
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def items(self) -> Iterator[Tuple[str, Any]]:
        """``(omf_name, last value)`` for every property present."""
        for name in self.property_names():
            yield name, self.get(name)

    def to_dict(self, deref: bool = False) -> Dict[str, Any]:
        return {n: (self._deref(v) if deref else v) for n, v in self.items()}

    @classmethod
    def known_properties(cls) -> "List[str]":
        """Every OMF property name this class understands, typed or structural."""
        return list(cls._propertydefs_by_omf) + list(cls._structural_properties)

    def type_of(self, omf_name: str) -> Optional[str]:
        """The OMF type name the file declares for ``omf_name``."""
        container = self.root.container
        for e in self._entries:
            if container.name_of(e.property_id) == omf_name:
                return container.name_of(e.type_id)
        return None

    def referenced_ids(self) -> List[int]:
        """Object IDs this object points at, via ObjRef and ObjRefArray."""
        container = self.root.container
        out: List[int] = []
        for e in self._entries:
            type_name = container.name_of(e.type_id)
            if type_name not in ("omfi:ObjRef", "omfi:ObjRefArray"):
                continue
            value = datatypes.decode(type_name, container.entry_bytes(e),
                                     container.label.endian)
            if isinstance(value, list):
                out.extend(value)
            elif isinstance(value, int):
                out.append(value)
        return out

    def references(self) -> "List[MDBObject]":
        root = self.root
        return [o for o in (root.object(i) for i in self.referenced_ids()) if o is not None]

    # -- niceties ----------------------------------------------------------
    def __eq__(self, other):
        return (isinstance(other, MDBObject)
                and other.object_id == self.object_id
                and other._rootref() is self._rootref())

    def __hash__(self):
        return hash((id(self._rootref()), self.object_id))

    def _repr_extra(self) -> str:
        return ""

    def __repr__(self):
        cid = self.class_name or "????"
        extra = self._repr_extra()
        return "<%s %s 0x%x%s>" % (cid, type(self).__name__, self.object_id,
                                   (" " + extra) if extra else "")
