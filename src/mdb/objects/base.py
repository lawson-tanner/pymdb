"""The two objects everything else hangs off: :class:`OMFObject` and ``HEAD``.

``HEAD`` is unusual -- it shares object 1 with Bento's own container object, so
the OMF layer and the container layer describe the same TOC entries from two
directions.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List

from ..core import MDBObject, PropertyDef as P, register_class

if TYPE_CHECKING:  # pragma: no cover
    from .trackgroups import Mob

__all__ = ["OMFObject", "Header"]


class OMFObject(MDBObject):
    """Common ancestry: every OMF object carries a class tag and a version.

    ``AMEVersion`` is declared for nearly every class in the schema but written
    for none of them in the reference samples; it is bound here once rather
    than repeated on ninety subclasses, since an absent property simply reads
    as ``None``.
    """

    __slots__ = ()
    propertydefs = [
        P("obj_id", "OMFI:ObjID", doc="the class 4CC"),
        P("minor_version", "OMFI:MinorVersion"),
    ]


@register_class
class Header(OMFObject):
    """The OMFi ``HEAD``, which shares object 1 with Bento's container object.

    Its four aggregate indexes are written at close time, which is why they
    sit in their own region of the heap starting exactly at
    :attr:`container_offset_at_close`.
    """

    class_id = "HEAD"
    __slots__ = ()
    propertydefs = [
        P("byte_order", "OMFI:ByteOrder", doc="'II' or 'MM', re-declared at the OMF layer"),
        P("version", "OMFI:Version"),
        P("last_modified", "OMFI:LastModified", doc="when the database was written"),
        P("object_spine", "OMFI:ObjectSpine", deref=True, doc="every top-level mob"),
        P("source_mobs", "OMFI:SourceMobs", doc="MobIndex: short UID -> source mob"),
        P("composition_mobs", "OMFI:CompositionMobs", doc="MobIndex: short UID -> composition mob"),
        P("class_dictionary", "OMFI:ClassDictionary", deref=True, doc="CLSD objects"),
        P("num_del_mobs", "OMFI:NumDelMobs"),
        P("del_blobs_size", "OMFI:DelBlobsSize"),
        P("container_offset_at_close", "OMFI:ContainerOffsetAtClose",
          doc="heap seam between object values and close-time index values"),
        P("toc_offset_at_close", "OMFI:TOCOffsetAtClose",
          doc="stale in both reference samples; a candidate dirty-close breadcrumb"),
        # declared in the schema of both samples, written in neither -- an MDB
        # is a media index, not an interchange file, so the provenance and
        # media-data indexes an OMF composition would carry stay empty.
        P("author", "OMFI:Author"),
        P("copyright", "OMFI:Copyright"),
        P("date", "OMFI:Date"),
        P("character_set", "OMFI:CharacterSet"),
        P("media_data", "OMFI:MediaData", deref=True,
          doc="index of embedded essence; empty in an MDB, which references media rather than holding it"),
        P("external_files", "OMFI:ExternalFiles", deref=True),
        P("blobs", "OMFI:Blobs"),
        P("attributes", "OMFI:Attributes", deref=True),
    ]

    def mobs(self) -> "List[Mob]":
        """Top-level mobs, from ``ObjectSpine``."""
        from .trackgroups import Mob
        return [o for o in (self.object_spine or []) if isinstance(o, Mob)]

    def _repr_extra(self):
        spine = self.get("OMFI:ObjectSpine") or []
        return "%d mobs" % len(spine)
