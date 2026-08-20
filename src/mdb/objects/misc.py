"""The odds and ends: links, markers, list containers, class descriptors.

What these have in common is that they hang off other objects rather than
standing on their own.  Two of them matter constantly in an MDB -- ``MCBR``
answers "which bin is this clip in?" and ``MCMR`` answers "where in the
timeline?" -- and the rest are declared by the schema against the day a file
uses them.
"""
from __future__ import annotations

from typing import List, Optional

from ..core import PropertyDef as P, register_class
from .base import OMFObject

__all__ = ["BinLink", "MobReference", "Marker", "TimeCrumbList", "SortedList",
           "ListItem", "ClassDescriptor", "MediaFileLink", "MediaFileBlock",
           "ControlCode", "AttributeClip", "MediaStreamProject", "Domain",
           "SoundDesignerLink", "UserProperty"]


@register_class
class BinLink(OMFObject):
    """``MCBR`` -- mob to bin: which ``.avb`` bins reference this media."""

    class_id = "MCBR"
    __slots__ = ()
    propertydefs = [
        P("bin_id_high", "OMFI:MCBR:MC:binID.high"),
        P("bin_id_low", "OMFI:MCBR:MC:binID.low"),
        P("bin_name_legacy", "OMFI:MCBR:MC:binName"),
        P("bin_name_utf8", "OMFI:MCBR:MC:binNameUTF8"),
        P("ame_version", "OMFI:MCBR:AMEVersion"),
    ]

    @property
    def bin_name(self) -> Optional[str]:
        return self.bin_name_utf8 or self.bin_name_legacy

    @property
    def bin_id(self) -> Optional[int]:
        hi, lo = self.bin_id_high, self.bin_id_low
        if hi is None or lo is None:
            return None
        return ((hi & 0xFFFFFFFF) << 32) | (lo & 0xFFFFFFFF)

    def _repr_extra(self):
        return repr(self.bin_name) if self.bin_name else ""


@register_class
class MobReference(OMFObject):
    """``MCMR`` -- a mob reference with a position, joined by MobID."""

    class_id = "MCMR"
    __slots__ = ()
    propertydefs = [
        P("mob_id", "OMFI:MCMR:MC:MobID"),
        P("position", "OMFI:MCMR:MC:Position"),
        # the schema declares both the MC-prefixed and bare spellings; only
        # the MC ones are written in either reference sample
        P("mob_id_bare", "OMFI:MCMR:MobID"),
        P("position_bare", "OMFI:MCMR:Position"),
    ]

    @property
    def mob(self):
        """The mob this reference names, or ``None`` if the file has no such mob."""
        mob_id = self.mob_id or self.mob_id_bare
        return self.root.mob_by_id(mob_id) if mob_id is not None else None

    def _repr_extra(self):
        return "pos=%s" % self.position


@register_class
class ClassDescriptor(OMFObject):
    """``CLSD`` -- one entry of HEAD's class dictionary.

    The dictionary declares only Avid's *extension* classes and their
    inheritance; built-in OMF1 classes are assumed known and never appear.
    """

    class_id = "CLSD"
    __slots__ = ()
    propertydefs = [
        P("class_4cc", "OMFI:CLSD:ClassID"),
        P("parent", "OMFI:CLSD:ParentClass", deref=True),
    ]

    @property
    def parent_4cc(self) -> Optional[str]:
        parent = self.parent
        return parent.class_4cc if isinstance(parent, ClassDescriptor) else None

    def _repr_extra(self):
        parent = self.parent_4cc
        return "%s%s" % (self.class_4cc, " -> " + parent if parent else "")


@register_class
class Marker(MobReference):
    """``TMBC`` -- a locator/marker: a coloured note pinned to a frame.

    Modelled as a :class:`MobReference` subclass because that is what pyavb
    found in the AVB container and the property sets agree.  Note that the
    MDB class dictionary declares ``TMBC`` and ``MCMR`` as *separate* roots
    with no parent, so this inheritance is pyavb's reading rather than the
    file's own claim; nothing depends on it, since properties are looked up by
    OMF name either way.
    """

    class_id = "TMBC"
    __slots__ = ()
    propertydefs = [
        P("name", "OMFI:TMBC:Name"),
        P("comp_offset", "OMFI:TMBC:MC:CompOffset", doc="frames from the start of the component"),
        P("offset", "OMFI:TMBC:Offset"),
        P("marker_attributes", "OMFI:TMBC:MC:Attributes", deref=True),
        P("attrs", "OMFI:TMBC:Attrs", deref=True),
        P("color", "OMFI:TMBC:MC:CarbonAPI::RGBColor",
          doc="three 16-bit RGB components, in the classic Mac OS RGBColor layout"),
        P("simple_color", "OMFI:TMBC:Color"),
        P("parent", "OMFI:TMBC:Parent", deref=True),
        P("handled_bad_control_codes", "OMFI:TMBC:MC:handledBadControlCodes"),
    ]

    @property
    def rgb(self) -> Optional[tuple]:
        """The marker colour as ``(r, g, b)``, each 0-65535, if one is set."""
        value = self.color
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return tuple(value[:3])
        return None

    def _repr_extra(self):
        return "%r @%s" % (self.name, self.comp_offset)


@register_class
class TimeCrumbList(OMFObject):
    """``TMCS`` -- the list of markers ("crumbs") on a track."""

    class_id = "TMCS"
    __slots__ = ()
    propertydefs = [
        P("crumbs", "OMFI:TMCS:MC:Crumbs", deref=True),
        P("num_crumbs", "OMFI:TMCS:MC:NumCrumbs"),
        P("crumbs_bare", "OMFI:TMCS:Crumbs", deref=True),
        P("num_crumbs_bare", "OMFI:TMCS:NumCrumbs"),
        P("crumb", "OMFI:TMCS:Crumb", deref=True, multi=True),
    ]

    def markers(self) -> "List[Marker]":
        refs = self.crumbs if self.crumbs is not None else self.crumbs_bare
        if refs is None:
            return []
        if not isinstance(refs, list):
            refs = [refs]
        return [r for r in refs if isinstance(r, Marker)]

    def __iter__(self):
        return iter(self.markers())

    def _repr_extra(self):
        return "%d crumbs" % len(self.markers())


@register_class
class SortedList(OMFObject):
    """``SMLS`` -- a fixed-stride list of records stored as one blob.

    ``ListItems`` is ``ListCount`` records of ``ItemSize`` bytes each rather
    than a list of objects, so :meth:`records` slices it.  ``FXPS`` inherits
    from this in the class dictionary of both samples.
    """

    class_id = "SMLS"
    __slots__ = ()
    propertydefs = [
        P("list_items", "OMFI:SMLS:MC:ListItems"),
        P("list_count", "OMFI:SMLS:MC:ListCount"),
        P("item_size", "OMFI:SMLS:MC:ItemSize"),
        P("entry_number", "OMFI:SMLS:MC:EntryNumber"),
    ]

    def records(self) -> List[bytes]:
        """The blob sliced into fixed-size records.

        Returns ``[]`` rather than guessing when the stride is missing or the
        blob does not divide by it -- a partial record is a sign the file is
        damaged, not something to paper over.
        """
        data, size = self.list_items, self.item_size
        if not isinstance(data, (bytes, bytearray)) or not size or size <= 0:
            return []
        count = self.list_count
        if count is None:
            count = len(data) // size
        return [bytes(data[i * size:(i + 1) * size]) for i in range(count)
                if (i + 1) * size <= len(data)]

    def _repr_extra(self):
        return "%s x %s bytes" % (self.list_count, self.item_size)


@register_class
class ListItem(OMFObject):
    """``LITM`` -- one entry of a list, carrying its payload as a blob."""

    class_id = "LITM"
    __slots__ = ()
    propertydefs = [P("entry_data", "OMFI:LITM:MC:EntryData")]


@register_class
class MediaFileLink(OMFObject):
    """``MFML`` -- the file-level twin of ``MSML``.

    Where ``MSML`` names the volume a mob's media was last seen on, ``MFML``
    names it for a single file, keyed by a 64-bit link UID split across two
    32-bit properties.
    """

    class_id = "MFML"
    __slots__ = ()
    propertydefs = [
        P("last_known_volume", "OMFI:MFML:LastKnownVolume"),
        P("link_uid_high", "OMFI:MFML:LinkUIDHigh"),
        P("link_uid_low", "OMFI:MFML:LinkUIDLow"),
        P("track_type", "OMFI:MFML:TrackType"),
    ]

    @property
    def link_uid(self) -> Optional[int]:
        hi, lo = self.link_uid_high, self.link_uid_low
        if hi is None or lo is None:
            return None
        return ((hi & 0xFFFFFFFF) << 32) | (lo & 0xFFFFFFFF)

    def _repr_extra(self):
        return repr(self.last_known_volume) if self.last_known_volume else ""


@register_class
class MediaFileBlock(OMFObject):
    """``MFMB`` -- one contiguous run of bytes inside a media file."""

    class_id = "MFMB"
    __slots__ = ()
    propertydefs = [
        P("byte_offset", "OMFI:MFMB:ByteOffset"),
        P("byte_length", "OMFI:MFMB:ByteLength"),
        P("is_slide", "OMFI:MFMB:IsSlide"),
    ]

    def _repr_extra(self):
        return "%s+%s" % (self.byte_offset, self.byte_length)


@register_class
class ControlCode(OMFObject):
    """``CNSC`` -- a control code with a rational value, used on control tracks."""

    class_id = "CNSC"
    __slots__ = ()
    propertydefs = [
        P("control_code", "OMFI:CNSC:ControlCode"),
        P("control_sub_code", "OMFI:CNSC:ControlSubCode"),
        P("control_type_code", "OMFI:CNSC:ControlTypeCode"),
        P("numerator", "OMFI:CNSC:Numerator"),
        P("denominator", "OMFI:CNSC:Denominator"),
    ]


@register_class
class AttributeClip(OMFObject):
    """``ATCP`` -- a clip whose whole content is an attribute list."""

    class_id = "ATCP"
    __slots__ = ()
    propertydefs = [
        P("attributes", "OMFI:ATCP:Attributes", deref=True),
        P("version", "OMFI:ATCP:Version"),
    ]


@register_class
class MediaStreamProject(OMFObject):
    """``MSP`` -- project and library metadata attached to a media stream."""

    class_id = "MSP"
    __slots__ = ()
    propertydefs = [
        P("project_data", "OMFI:MSP:ProjectData"),
        P("library_data", "OMFI:MSP:LibraryData"),
    ]


# --------------------------------------------------------------------------
# Classes the schema names but says nothing about.
#
# Each of these is declared in the name registry of both reference samples
# with exactly one property -- ``AMEVersion``, which every class has and no
# object writes.  So the file tells us the class exists and nothing else.
# They are bound anyway, because a typed object with the right name and a
# readable property bag beats a generic one, and because the day a file uses
# one, the gap should be obvious rather than silent.
# --------------------------------------------------------------------------
@register_class
class Domain(OMFObject):
    """``DOMN`` -- a domain.  Purpose unverified.

    Sits next to ``DOML`` (:class:`~mdb.objects.locators.DomainLocator`) in the
    schema, which suggests the pair is a name and a reference to it, but
    nothing in either sample confirms that.
    """

    class_id = "DOMN"
    __slots__ = ()


@register_class
class SoundDesignerLink(OMFObject):
    """``SDSL`` -- purpose unverified.

    The neighbouring ``SD2D``
    (:class:`~mdb.objects.descriptors.SoundDesignerDescriptor`) makes a Sound
    Designer link the obvious reading, and ``MACL`` declares ``SDSAddress`` and
    ``SDSMobID`` properties that would fit.  Unconfirmed.
    """

    class_id = "SDSL"
    __slots__ = ()


@register_class
class UserProperty(OMFObject):
    """``USPR`` -- purpose unverified.

    Most likely a user-defined property, by analogy with ``AVUP``
    (:class:`~mdb.objects.parameters.UserParameter`), but the schema declares
    no properties for it and neither sample contains one.
    """

    class_id = "USPR"
    __slots__ = ()
