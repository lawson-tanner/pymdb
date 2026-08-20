"""``TRKG`` and its descendants -- components made of parallel tracks.

``MOBJ`` is the one that matters in an MDB: a mob is the unit of media
identity, and everything else joins to it.  The rest of the family (selectors,
effects, time warps) belongs to composition editing and reaches an MDB only
when a rendered effect produces media of its own -- see
:mod:`mdb.objects.effects` for those.
"""
from __future__ import annotations

from typing import Iterator, List, Optional

from .. import enums
from ..core import MDBObject, PropertyDef as P, register_class
from .attributes import AttributeList
from .base import OMFObject
from .components import Component, Sequence, SourceClip
from .descriptors import MediaDescriptor
from .locators import Locator, MediaStreamLink
from .misc import BinLink, MobReference

__all__ = ["TrackGroup", "Mob", "RepeatSet", "Track", "Selector"]


@register_class
class TrackGroup(Component):
    """``TRKG`` -- a component made of parallel tracks."""

    class_id = "TRKG"
    __slots__ = ()
    propertydefs = [
        P("tracks", "OMFI:TRKG:Tracks", deref=True),
        P("group_length", "OMFI:TRKG:GroupLength"),
        P("mode", "OMFI:TRKG:MC:Mode"),
        P("type_code", "OMFI:TRKG:TypeCode"),
        P("numerator", "OMFI:TRKG:Numerator"),
        P("denominator", "OMFI:TRKG:Denominator"),
        P("num_scalars", "OMFI:TRKG:NumScalars"),
        P("control_scalars", "OMFI:TRKG:ControlScalars"),
        P("isolation", "OMFI:TRKG:Isolation"),
        P("locks_suspended", "OMFI:TRKG:LocksSuspended"),
    ]

    def components(self) -> Iterator[MDBObject]:
        """The component on each track, skipping tracks that carry none."""
        for track in (self.tracks or []):
            comp = getattr(track, "component", None)
            if comp is not None:
                yield comp


@register_class
class Mob(TrackGroup):
    """``MOBJ`` -- a media object: the unit of media identity.

    Everything joins on :attr:`mob_id`.  ``PhysicalMedia`` leads to the
    descriptor (codec, raster, rate) and from there to the locators that name
    the media file on disk.
    """

    class_id = "MOBJ"
    __slots__ = ()
    propertydefs = [
        P("mob_id", "OMFI:MOBJ:MobID", doc="32-byte SMPTE UMID"),
        P("usage_code", "OMFI:MOBJ:UsageCode", enum=enums.USAGE_CODE),
        P("physical_media", "OMFI:MOBJ:PhysicalMedia", deref=True),
        P("start_position", "OMFI:MOBJ:StartPosition"),
        P("last_modified", "OMFI:MOBJ:LastModified"),
        P("creation_time", "OMFI:MOBJ:_CreationTime"),
    ]

    # -- convenience walks -------------------------------------------------
    @property
    def descriptor(self) -> "Optional[MediaDescriptor]":
        d = self.physical_media
        return d if isinstance(d, MediaDescriptor) else None

    def locators(self) -> "List[Locator]":
        d = self.descriptor
        return d.locators() if d else []

    def paths(self) -> List[str]:
        """Every distinct file path this mob's locators name, UTF-8 preferred.

        MSML links share the locator list but carry a volume rather than a
        path, so they contribute nothing here -- see :meth:`volumes`.
        """
        out: List[str] = []
        for loc in self.locators():
            for p in loc.all_paths():
                if p and p not in out:
                    out.append(p)
        return out

    def sequences(self) -> "List[Sequence]":
        out = []
        for track in (self.tracks or []):
            comp = getattr(track, "component", None)
            if isinstance(comp, Sequence):
                out.append(comp)
        return out

    def source_clips(self) -> "List[SourceClip]":
        """Every SCLP under this mob's tracks (one level of sequence deep)."""
        out: List[SourceClip] = []
        for track in (self.tracks or []):
            comp = getattr(track, "component", None)
            if isinstance(comp, SourceClip):
                out.append(comp)
            elif isinstance(comp, Sequence):
                out.extend(c for c in comp if isinstance(c, SourceClip))
        return out

    def sources(self) -> "List[Mob]":
        """The previous-generation mobs this mob derives from."""
        out: List[Mob] = []
        for clip in self.source_clips():
            mob = clip.source_mob()
            if mob is not None and mob not in out:
                out.append(mob)
        return out

    def derivation_chain(self, max_depth: int = 32) -> "List[Mob]":
        """Walk ``SCLP:SourceID`` upstream until the 0-0-0 sentinel.

        Cycles and runaway depth are guarded: a damaged file should not hang
        the caller.
        """
        chain: List[Mob] = [self]
        seen = {self.object_id}
        current = self
        while len(chain) < max_depth:
            nxt = next((m for m in current.sources() if m.object_id not in seen), None)
            if nxt is None:
                break
            chain.append(nxt)
            seen.add(nxt.object_id)
            current = nxt
        return chain

    def stream_links(self) -> "List[MediaStreamLink]":
        """The MSML volume links for this mob.

        MSML is a locator subclass (``MSML -> TXTL`` in the class dictionary),
        so it hangs off the descriptor alongside the file locators -- it is not
        found by scanning for a matching MobID, though it does carry a copy of
        one for the reverse lookup.
        """
        out = [l for l in self.locators() if isinstance(l, MediaStreamLink)]
        if out:
            return out
        # a mob without its own descriptor may still be named by an MSML
        return [l for l in self.root.links_for(self.mob_id)
                if isinstance(l, MediaStreamLink)]

    def volumes(self) -> List[str]:
        """Distinct last-known volumes this mob's media was seen on."""
        out: List[str] = []
        for link in self.stream_links():
            if link.volume and link.volume not in out:
                out.append(link.volume)
        return out

    def bin_links(self) -> "List[BinLink]":
        """The MCBR bin links for this mob.

        MCBR carries no MobID.  It is reached through the attribute tree:
        ``MOBJ -> CPNT:Attributes -> ATTR -> ATTB('_ORG_BIN', kind=object) -> MCBR``.
        """
        out: List[BinLink] = []
        attrs = self.attribute_list()
        if attrs is None:
            return out
        for attr in attrs:
            value = attr.value
            if isinstance(value, BinLink):
                out.append(value)
            elif isinstance(value, AttributeList):
                for nested in value:
                    if isinstance(nested.value, BinLink):
                        out.append(nested.value)
        return out

    def bins(self) -> List[str]:
        """Names of the ``.avb`` bins that reference this mob."""
        out: List[str] = []
        for link in self.bin_links():
            if link.bin_name and link.bin_name not in out:
                out.append(link.bin_name)
        return out

    def mob_references(self) -> "List[MobReference]":
        """MCMR objects hanging off this mob's attribute tree."""
        out: List[MobReference] = []
        attrs = self.attribute_list()
        if attrs is None:
            return out
        for attr in attrs:
            value = attr.value
            if isinstance(value, MobReference):
                out.append(value)
        return out

    def _repr_extra(self):
        bits = []
        if self.name:
            bits.append(repr(self.name))
        mob_id = self.get("OMFI:MOBJ:MobID")
        if mob_id is not None:
            bits.append(str(getattr(mob_id, "short_uid", mob_id)))
        return " ".join(bits)


@register_class
class RepeatSet(TrackGroup):
    """``RSET`` -- Avid extension: a set of alternate representations."""

    class_id = "RSET"
    __slots__ = ()
    propertydefs = [P("rep_set_type", "OMFI:RSET:repSetType")]


@register_class
class Track(OMFObject):
    """``TRAK`` -- one slot of a track group."""

    class_id = "TRAK"
    __slots__ = ()
    propertydefs = [
        P("component", "OMFI:TRAK:TrackComponent", deref=True),
        P("label_number", "OMFI:TRAK:LabelNumber"),
        P("opt_flags", "OMFI:TRAK:OptFlags"),
        P("filler_proxy", "OMFI:TRAK:FillerProxy", deref=True),
        P("attributes", "OMFI:TRAK:Attributes", deref=True),
        P("session_attrs", "OMFI:TRAK:SessionAttrs", deref=True),
        P("start_position", "OMFI:TRAK:StartPos"),
        P("control_code", "OMFI:TRAK:ControlCode"),
        P("control_sub_code", "OMFI:TRAK:ControlSubCode"),
        P("lock_number", "OMFI:TRAK:LockNubmer",
          doc="spelled 'LockNubmer' in the schema -- Avid's typo, preserved"),
        P("track_label", "OMFI:trkt:Track.trkLNum",
          doc="the lowercase 'trkt' spelling, used when a track is written inline"),
        P("track_type", "OMFI:trkt:Track.trkType", enum=enums.TRACK_TYPE),
    ]

    @property
    def track_kind(self):
        comp = self.component
        return getattr(comp, "track_kind", None) if comp is not None else None

    @property
    def track_kind_name(self) -> str:
        return enums.label(enums.TRACK_TYPE, self.track_kind, "track_kind")

    def _repr_extra(self):
        return "label=%s %s" % (self.label_number, self.track_kind_name)


@register_class
class Selector(TrackGroup):
    """``SLCT`` -- one track chosen from several alternatives.

    The classic use is a multi-camera group or an effect's "before" leg:
    :attr:`selected` indexes into :attr:`~TrackGroup.tracks`, and the rest are
    kept but not played.  Absent from both reference samples.
    """

    class_id = "SLCT"
    __slots__ = ()
    propertydefs = [
        P("is_ganged", "OMFI:SLCT:IsGanged"),
        P("selected", "OMFI:SLCT:SelectedTrack", doc="index into tracks"),
    ]

    def selected_track(self) -> "Optional[Track]":
        """The chosen track, or ``None`` if the index does not address one."""
        tracks = self.tracks or []
        index = self.selected
        if index is None or not (0 <= index < len(tracks)):
            return None
        track = tracks[index]
        return track if isinstance(track, Track) else None

    def _repr_extra(self):
        return "selected=%s of %d" % (self.selected, len(self.get("OMFI:TRKG:Tracks") or []))
