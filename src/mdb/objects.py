"""The OMF / Avid class vocabulary.

The property tables below were derived by census over the two reference
samples (every property that occurs on every class, with its declared type),
then named against the OMF Interchange 2.1 specification and pyavb's
equivalent vocabulary for the AVB container.

The hierarchy mirrors OMF's own, which is why a ``MOBJ`` answers to
``CPNT``, ``TRKG`` and ``MOBJ`` properties alike::

    OMFObject
      Component (CPNT)
        Clip (CLIP) -> SourceClip (SCLP), Filler (FILL), Timecode (TCCP),
                       TrackRef (TRKR)
        Sequence (SEQU)
        TrackGroup (TRKG) -> Mob (MOBJ), RepeatSet (RSET)
      Track (TRAK)
      MediaDescriptor (MDES)
        FileDescriptor (MDFL)
          DigitalImageDescriptor (DIDD) -> CDCI, RGBA
          PCMADescriptor (PCMA)
      Locator -> WINL, DOSL, MACL, UNXL, TXTL -> MSML
      Attribute list (ATTR) / attribute (ATTB)
      Class descriptor (CLSD), bin link (MCBR), mob reference (MCMR)
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from . import enums
from .core import MDBObject, PropertyDef as P, register_class
from .datatypes import Opaque
from .mobid import MobID, ShortUID

__all__ = [
    "OMFObject", "Header", "Component", "Clip", "SourceClip", "Filler",
    "Timecode", "TrackRef", "Sequence", "TrackGroup", "Mob", "RepeatSet",
    "Track", "MediaDescriptor", "FileDescriptor", "DigitalImageDescriptor",
    "CDCIDescriptor", "RGBADescriptor", "PCMADescriptor", "Locator",
    "WindowsLocator", "DOSLocator", "MacLocator", "UnixLocator", "TextLocator",
    "MediaStreamLink", "BinLink", "MobReference", "AttributeList", "Attribute",
    "ClassDescriptor",
]


# --------------------------------------------------------------------------
class OMFObject(MDBObject):
    """Common ancestry: every OMF object carries a class tag and a version."""

    __slots__ = ()
    propertydefs = [
        P("obj_id", "OMFI:ObjID", doc="the class 4CC"),
        P("minor_version", "OMFI:MinorVersion"),
    ]


# --------------------------------------------------------------------------
# HEAD -- overlaid on Bento's container object (object 1)
# --------------------------------------------------------------------------
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
    ]

    def mobs(self) -> "List[Mob]":
        """Top-level mobs, from ``ObjectSpine``."""
        return [o for o in (self.object_spine or []) if isinstance(o, Mob)]

    def _repr_extra(self):
        spine = self.get("OMFI:ObjectSpine") or []
        return "%d mobs" % len(spine)


# --------------------------------------------------------------------------
# components
# --------------------------------------------------------------------------
class Component(OMFObject):
    """``CPNT`` -- anything with an edit rate and a track kind."""

    __slots__ = ()
    propertydefs = [
        P("edit_rate", "OMFI:CPNT:EditRate"),
        P("name", "OMFI:CPNT:Name"),
        P("track_kind", "OMFI:CPNT:TrackKind", enum=enums.TRACK_TYPE),
        P("attributes", "OMFI:CPNT:Attributes", deref=True),
    ]

    def attribute_list(self) -> "Optional[AttributeList]":
        attrs = self.attributes
        return attrs if isinstance(attrs, AttributeList) else None

    def attribute(self, name: str, default: Any = None) -> Any:
        """Look up one Avid attribute by name, e.g. ``mob.attribute('_PJ')``."""
        attrs = self.attribute_list()
        return attrs.get_attribute(name, default) if attrs else default

    def attribute_dict(self) -> Dict[str, Any]:
        attrs = self.attribute_list()
        return attrs.to_attribute_dict() if attrs else {}


class Clip(Component):
    """``CLIP`` -- a component with a duration."""

    __slots__ = ()
    propertydefs = [P("length", "OMFI:CLIP:Length")]


@register_class
class SourceClip(Clip):
    """``SCLP`` -- the derivation link.

    ``source_id`` names the previous-generation mob by short UID; the OMF1
    sentinel 0-0-0 means "this is the original".
    """

    class_id = "SCLP"
    __slots__ = ()
    propertydefs = [
        P("source_id", "OMFI:SCLP:SourceID"),
        P("source_position", "OMFI:SCLP:SourcePosition"),
        P("source_track", "OMFI:SCLP:SourceTrack"),
    ]

    @property
    def is_original(self) -> bool:
        """True when this clip has no upstream source (the 0-0-0 sentinel)."""
        uid = self.source_id
        return uid is None or getattr(uid, "is_null", False)

    def source_mob(self) -> "Optional[Mob]":
        """Resolve ``source_id`` to a mob.

        Media Composer writes a full 32-byte UMID here, though OMF1 allows the
        12-byte short UID that HEAD's MobIndex uses; both are handled, and both
        ultimately match on the 8-byte material number.
        """
        uid = self.source_id
        if uid is None or getattr(uid, "is_null", True):
            return None
        root = self.root
        if isinstance(uid, MobID):
            return root.mob_by_id(uid) or root.mob_by_short_uid(uid.short_uid)
        if isinstance(uid, ShortUID):
            return root.mob_by_short_uid(uid)
        return None

    def _repr_extra(self):
        source = "original" if self.is_original else "src=%s" % self.source_id
        return "%s pos=%s" % (source, self.source_position)


@register_class
class Filler(Clip):
    """``FILL`` -- silence / black."""

    class_id = "FILL"
    __slots__ = ()


@register_class
class Timecode(Clip):
    """``TCCP`` -- a timecode track's start, rate and flags."""

    class_id = "TCCP"
    __slots__ = ()
    propertydefs = [
        P("start_tc", "OMFI:TCCP:StartTC", doc="start timecode, in frames"),
        P("fps", "OMFI:TCCP:FPS"),
        P("flags", "OMFI:TCCP:Flags", doc="bit 0 is drop-frame in OMF"),
    ]

    @property
    def drop_frame(self) -> Optional[bool]:
        flags = self.flags
        return None if flags is None else bool(flags & 1)

    def timecode_string(self) -> Optional[str]:
        """Format ``start_tc`` as ``HH:MM:SS:FF`` (``;`` for drop-frame)."""
        start, fps = self.start_tc, self.fps
        if start is None or not fps:
            return None
        frames = int(start)
        sep = ";" if self.drop_frame else ":"
        f = frames % fps
        total_seconds = frames // fps
        return "%02d:%02d:%02d%s%02d" % (
            total_seconds // 3600, (total_seconds // 60) % 60,
            total_seconds % 60, sep, f)

    def _repr_extra(self):
        return self.timecode_string() or ""


@register_class
class TrackRef(Clip):
    """``TRKR`` -- a reference to another track in the same mob."""

    class_id = "TRKR"
    __slots__ = ()
    propertydefs = [
        P("relative_scope", "OMFI:TRKR:RelativeScope"),
        P("relative_track", "OMFI:TRKR:RelativeTrack"),
    ]


@register_class
class Sequence(Component):
    """``SEQU`` -- an ordered list of components on one track."""

    class_id = "SEQU"
    __slots__ = ()
    propertydefs = [P("components", "OMFI:SEQU:Sequence", deref=True)]

    def __iter__(self) -> Iterator[MDBObject]:
        return iter(self.components or [])

    def __len__(self):
        return len(self.get("OMFI:SEQU:Sequence") or [])

    def _repr_extra(self):
        return "%d components" % len(self)


class TrackGroup(Component):
    """``TRKG`` -- a component made of parallel tracks."""

    __slots__ = ()
    propertydefs = [
        P("tracks", "OMFI:TRKG:Tracks", deref=True),
        P("group_length", "OMFI:TRKG:GroupLength"),
        P("mode", "OMFI:TRKG:MC:Mode"),
    ]


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


# --------------------------------------------------------------------------
# descriptors
# --------------------------------------------------------------------------
@register_class
class MediaDescriptor(OMFObject):
    """``MDES`` -- the base "physical media" descriptor.

    ``MDES:Locator`` is an ObjRefArray, not a single reference: one descriptor
    can name several locators.
    """

    class_id = "MDES"
    __slots__ = ()
    propertydefs = [
        P("locator_refs", "OMFI:MDES:Locator", deref=True),
        P("mob_kind", "OMFI:MDES:MobKind", enum=enums.PHYSICAL_MOB_TYPE),
        P("intermediate", "OMFI:MDES:MC:Intermediate"),
        P("acf_uid", "OMFI:AMDL:acfUID"),
    ]

    def locators(self) -> "List[Locator]":
        refs = self.locator_refs
        if refs is None:
            return []
        if not isinstance(refs, list):
            refs = [refs]
        return [r for r in refs if isinstance(r, Locator)]

    def summary(self) -> str:
        """One line describing the essence, for listings."""
        return self.mob_kind_name


@register_class
class FileDescriptor(MediaDescriptor):
    """``MDFL`` -- media stored in a file: length, rate, and where it starts."""

    class_id = "MDFL"
    __slots__ = ()
    propertydefs = [
        P("length", "OMFI:MDFL:Length", doc="duration in sample_rate units"),
        P("sample_rate", "OMFI:MDFL:SampleRate"),
        P("data_offset", "OMFI:MDFL:dataOffset", doc="byte offset of essence in the file"),
        P("is_omfi", "OMFI:MDFL:IsOMFI"),
    ]

    def summary(self) -> str:
        return "%s %s, %s samples" % (self.mob_kind_name, self.sample_rate, self.length)


@register_class
class DigitalImageDescriptor(FileDescriptor):
    """``DIDD`` -- picture essence geometry and coding.

    Avid writes the full OMF raster model (stored / sampled / display /
    valid rectangles, each as a numerator-denominator pair) plus its own
    ``DIDCompressMethod`` 4CC and the AAF-style ``EssenceCompression`` label.
    """

    class_id = "DIDD"
    __slots__ = ()
    propertydefs = [
        P("stored_width", "OMFI:DIDD:StoredWidth"),
        P("stored_height", "OMFI:DIDD:StoredHeight"),
        P("sampled_width", "OMFI:DIDD:SampledWidth"),
        P("sampled_height", "OMFI:DIDD:SampledHeight"),
        P("sampled_x_offset", "OMFI:DIDD:SampledXOffset"),
        P("sampled_y_offset", "OMFI:DIDD:SampledYOffset"),
        P("display_width", "OMFI:DIDD:DisplayWidth"),
        P("display_height", "OMFI:DIDD:DisplayHeight"),
        P("display_x_offset", "OMFI:DIDD:DisplayXOffset"),
        P("display_y_offset", "OMFI:DIDD:DisplayYOffset"),
        P("frame_layout", "OMFI:DIDD:FrameLayout", enum=enums.LAYOUT_TYPE),
        P("image_aspect_ratio", "OMFI:DIDD:ImageAspectRatio"),
        P("video_line_map", "OMFI:DIDD:VideoLineMap", multi=True,
          doc="genuinely multi-valued: one entry per field"),
        P("alpha_transparency", "OMFI:DIDD:AlphaTransparency"),
        P("compression", "OMFI:DIDD:Compression"),
        P("compress_method", "OMFI:DIDD:DIDCompressMethod", doc="Avid 4CC, e.g. 'RI00'"),
        P("essence_compression", "OMFI:DIDD:EssenceCompression", doc="SMPTE UL"),
        P("coding_equations", "OMFI:DIDD:CodingEquations"),
        P("color_primaries", "OMFI:DIDD:ColorPrimaries"),
        P("transfer_characteristic", "OMFI:DIDD:TransferCharacteristic"),
        P("resolution_id", "OMFI:DIDD:DIDResolutionID"),
        P("image_size", "OMFI:DIDD:DIDImageSize"),
        P("frame_sample_size", "OMFI:DIDD:FrameSampleSize"),
        P("first_frame_offset", "OMFI:DIDD:FirstFrameOffset"),
        P("frame_index_byte_order", "OMFI:DIDD:FrameIndexByteOrder"),
        P("offset_to_rle_frame_indexes", "OMFI:DIDD:OffsetToRLEFrameIndexes"),
        P("offset_to_frame_indexes", "OMFI:JPED:OffsetToFrameIndexes"),
        P("client_fill_start", "OMFI:DIDD:ClientFillStart"),
        P("client_fill_end", "OMFI:DIDD:ClientFillEnd"),
        P("image_alignment_factor", "OMFI:DIDD:ImageAlignmentFactor"),
        P("uniformness", "OMFI:DIDD:Uniformness"),
    ]

    @property
    def raster(self) -> Optional[str]:
        w, h = self.stored_width, self.stored_height
        return None if w is None or h is None else "%dx%d" % (w, h)

    def summary(self) -> str:
        parts = [p for p in (self.raster, self.compress_method,
                             str(self.sample_rate) if self.sample_rate else None) if p]
        return " ".join(parts) or self.mob_kind_name


@register_class
class CDCIDescriptor(DigitalImageDescriptor):
    """``CDCI`` -- colour-difference component image (Y'CbCr)."""

    class_id = "CDCI"
    __slots__ = ()
    propertydefs = [
        P("component_width", "OMFI:CDCI:ComponentWidth", doc="bit depth per component"),
        P("horizontal_subsampling", "OMFI:CDCI:HorizontalSubsampling"),
        P("vertical_subsampling", "OMFI:CDCI:VerticalSubsampling"),
        P("color_siting", "OMFI:CDCI:ColorSiting", enum=enums.COLOR_SITING),
        P("black_reference_level", "OMFI:CDCI:BlackReferenceLevel"),
        P("white_reference_level", "OMFI:CDCI:WhiteReferenceLevel"),
        P("color_range", "OMFI:CDCI:ColorRange"),
        P("alpha_sampled_width", "OMFI:CDCI:AlphaSamledWidth",
          doc="spelled 'AlphaSamled' in the file -- Avid's typo, preserved"),
        P("ignore_bw_ref_and_color_range", "OMFI:CDCI:IgnoreBWRefLevelAndColorRange"),
    ]

    @property
    def subsampling(self) -> Optional[str]:
        """Chroma subsampling as ``4:2:2`` / ``4:2:0`` / ``4:4:4``."""
        h, v = self.horizontal_subsampling, self.vertical_subsampling
        if not h:
            return None
        return {(1, 1): "4:4:4", (2, 1): "4:2:2", (2, 2): "4:2:0",
                (4, 1): "4:1:1"}.get((h, v or 1))

    def summary(self) -> str:
        bits = "%d-bit" % self.component_width if self.component_width else None
        return " ".join(p for p in (super().summary(), bits, self.subsampling) if p)


@register_class
class RGBADescriptor(DigitalImageDescriptor):
    """``RGBA`` -- RGB(A) image essence."""

    class_id = "RGBA"
    __slots__ = ()
    propertydefs = [
        P("pixel_layout", "OMFI:RGBA:PixelLayout"),
        P("pixel_structure", "OMFI:RGBA:PixelStructure"),
        P("component_min_ref", "OMFI:RGBA:ComponentMinRef"),
        P("component_max_ref", "OMFI:RGBA:ComponentMaxRef"),
        P("has_comp_min_ref", "OMFI:RGBA:HasCompMinRef"),
        P("has_comp_max_ref", "OMFI:RGBA:HasCompMaxRef"),
        P("offset_to_frame_indexes", "OMFI:RGBA:OffsetToFrameIndexes"),
        P("attributes", "OMFI:AMDL:Attributes", deref=True),
    ]


@register_class
class PCMADescriptor(FileDescriptor):
    """``PCMA`` -- linear PCM audio, with BWF peak-envelope metadata."""

    class_id = "PCMA"
    __slots__ = ()
    propertydefs = [
        P("num_channels", "OMFI:MDAU:NumChannels"),
        P("bits_per_sample", "OMFI:MDAU:BitsPerSample"),
        P("audio_sampling_rate", "OMFI:PCMA:AudioSamplingRate"),
        P("block_alignment", "OMFI:PCMA:BlockAlignment"),
        P("average_bytes_per_second", "OMFI:PCMA:AverageBytesPerSecond"),
        P("sequence_offset", "OMFI:PCMA:SequenceOffset"),
        P("audio_coding_format", "OMFI:PCMA:AudioCodingFormat"),
        P("audio_ref_level", "OMFI:PCMA:AudioRefLevel"),
        P("dial_norm", "OMFI:PCMA:DialNorm"),
        P("electro_spatial_formulation", "OMFI:PCMA:ElectroSpatialFormulation"),
        P("locked", "OMFI:PCMA:Locked"),
        P("has_peak_envelope_data", "OMFI:PCMA:HasPeakEnvelopeData"),
        P("peak_channel_count", "OMFI:PCMA:PeakChannelCount"),
        P("peak_frame_count", "OMFI:PCMA:PeakFrameCount"),
        P("peak_envelope_version", "OMFI:PCMA:PeakEnvelopeVersion"),
        P("peak_envelope_format", "OMFI:PCMA:PeakEnvelopeFormat"),
        P("peak_envelope_block_size", "OMFI:PCMA:PeakEnvelopeBlockSize"),
        P("peak_envelope_timestamp", "OMFI:PCMA:PeakEnvelopeTimestamp"),
        P("peak_of_peaks_offset", "OMFI:PCMA:PeakOfPeaksOffset"),
        P("points_per_peak_value", "OMFI:PCMA:PointsPerPeakValue"),
        P("version", "OMFI:PCMA:Version"),
    ]

    def summary(self) -> str:
        rate = self.audio_sampling_rate or self.sample_rate
        bits = []
        if rate:
            bits.append("%gkHz" % (float(rate) / 1000.0))
        if self.bits_per_sample:
            bits.append("%d-bit" % self.bits_per_sample)
        if self.num_channels:
            bits.append("%dch" % self.num_channels)
        return " ".join(bits) or self.mob_kind_name


# --------------------------------------------------------------------------
# locators
# --------------------------------------------------------------------------
class Locator(OMFObject):
    """Base for the file-locator classes: a path, in one or more spellings.

    Avid writes both a legacy code-page ``FL:PathName`` and a
    ``FL:PathNameUTF8`` twin, and a locator can carry more than one of either
    (an empty one plus the real path is common), so all values are exposed.
    """

    __slots__ = ()
    propertydefs = [
        P("path_name", "OMFI:FL:PathName"),
        P("path_name_utf8", "OMFI:FL:PathNameUTF8"),
    ]

    @property
    def path(self) -> Optional[str]:
        """The best available path: the last non-empty UTF-8 value, else legacy."""
        for candidate in reversed(self.values("OMFI:FL:PathNameUTF8")):
            if candidate:
                return candidate
        for candidate in reversed(self.values("OMFI:FL:PathName")):
            if candidate:
                return candidate
        return None

    def all_paths(self) -> List[str]:
        seen, out = set(), []
        for name in ("OMFI:FL:PathNameUTF8", "OMFI:FL:PathName"):
            for candidate in self.values(name):
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    out.append(candidate)
        return out

    def _repr_extra(self):
        p = self.path
        return repr(p) if p else ""


@register_class
class WindowsLocator(Locator):
    """``WINL`` -- a Windows path, usually UNC."""
    class_id = "WINL"
    __slots__ = ()


@register_class
class DOSLocator(Locator):
    """``DOSL`` -- a DOS path.  Declared in the schema; not seen in the samples."""
    class_id = "DOSL"
    __slots__ = ()


@register_class
class MacLocator(Locator):
    """``MACL`` -- a Macintosh path."""
    class_id = "MACL"
    __slots__ = ()


@register_class
class UnixLocator(Locator):
    """``UNXL`` -- a Unix path."""
    class_id = "UNXL"
    __slots__ = ()


@register_class
class TextLocator(Locator):
    """``TXTL`` -- a free-text locator; parent class of MSML."""
    class_id = "TXTL"
    __slots__ = ()


# --------------------------------------------------------------------------
# links -- these join by MobID *value*, not by object reference
# --------------------------------------------------------------------------
@register_class
class MediaStreamLink(TextLocator):
    """``MSML`` -- mob to volume: which drive the media was last seen on."""

    class_id = "MSML"
    __slots__ = ()
    propertydefs = [
        P("mob_id", "OMFI:MSML:MobID"),
        P("last_known_volume", "OMFI:MSML:LastKnownVolume"),
        P("last_known_volume_utf8", "OMFI:MSML:LastKnownVolumeUTF8"),
        P("domain_type", "OMFI:MSML:DomainType"),
    ]

    @property
    def volume(self) -> Optional[str]:
        return self.last_known_volume_utf8 or self.last_known_volume

    def _repr_extra(self):
        return repr(self.volume) if self.volume else ""


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
    ]


# --------------------------------------------------------------------------
# attributes -- where most Avid-specific data lives
# --------------------------------------------------------------------------
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
