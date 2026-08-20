"""``ATTR`` / ``ATTB`` -- where most Avid-specific data lives.

Attributes nest: an ``ATTB`` of kind *object* can point at another ``ATTR``,
at a locator, or at a bin link, so these form trees exactly as they do in AVB
bins.  Bin membership, project name and the source-file metadata Media
Composer shows in bin columns all arrive through here rather than through a
typed property.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .. import enums
from ..core import PropertyDef as P, register_class
from .base import OMFObject

__all__ = ["AttributeList", "Attribute"]


@register_class
class AttributeList(OMFObject):
    """``ATTR`` -- an ordered list of ``ATTB`` name/value pairs.

    Attributes nest: an ``ATTB`` of kind *object* can point at another ``ATTR``
    (or at a locator), so these form trees exactly as they do in AVB bins.
    """

    class_id = "ATTR"
    __slots__ = ()
    propertydefs = [P("attr_refs", "OMFI:ATTR:AttrRefs", deref=True)]

    def attributes(self) -> "List[Attribute]":
        refs = self.attr_refs or []
        return [r for r in refs if isinstance(r, Attribute)]

    def __iter__(self):
        return iter(self.attributes())

    def __len__(self):
        return len(self.get("OMFI:ATTR:AttrRefs") or [])

    def get_attribute(self, name: str, default: Any = None) -> Any:
        for attr in self.attributes():
            if attr.name == name:
                return attr.value
        return default

    def to_attribute_dict(self, recursive: bool = False, _depth: int = 0) -> Dict[str, Any]:
        """Flatten to ``{name: value}``; later duplicates win.

        With ``recursive``, nested ``ATTR`` values become nested dicts.  Depth
        is capped so a cyclic attribute tree cannot hang the caller.
        """
        out: Dict[str, Any] = {}
        for attr in self.attributes():
            value = attr.value
            if recursive and _depth < 16 and isinstance(value, AttributeList):
                value = value.to_attribute_dict(True, _depth + 1)
            out[attr.name] = value
        return out

    def _repr_extra(self):
        return "%d attributes" % len(self)


@register_class
class Attribute(OMFObject):
    """``ATTB`` -- one Avid attribute.

    :attr:`kind` says which value property is populated: 1 int, 2 string,
    3 object reference, 4 "bob" blob (``BobData`` plus ``BobSize``).
    :attr:`value` picks the right one for you.
    """

    class_id = "ATTB"
    __slots__ = ()
    propertydefs = [
        P("kind", "OMFI:ATTB:Kind", enum=enums.ATTR_KIND),
        P("name", "OMFI:ATTB:Name"),
        P("int_value", "OMFI:ATTB:IntAttribute"),
        P("string_value", "OMFI:ATTB:StringAttribute"),
        P("object_value", "OMFI:ATTB:ObjAttribute", deref=True),
        P("bob_data", "OMFI:ATTB:BobData"),
        P("bob_size", "OMFI:ATTB:BobSize"),
    ]

    @property
    def value(self) -> Any:
        """The populated value, chosen by :attr:`kind`.

        Falls back to whichever value property is present when the kind is
        unrecognised, so a new kind still yields data.
        """
        kind = self.kind
        if kind == 1:
            return self.int_value
        if kind == 2:
            return self.string_value
        if kind == 3:
            return self.object_value
        if kind == 4:
            return self.bob_data
        for name in ("int_value", "string_value", "object_value", "bob_data"):
            value = getattr(self, name)
            if value is not None:
                return value
        return None

    def _repr_extra(self):
        value = self.value
        if isinstance(value, (str, int)):
            return "%s=%r" % (self.name, value)
        return "%s (%s)" % (self.name, self.kind_name)
