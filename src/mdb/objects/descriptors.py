"""``MDES`` and its descendants -- what the essence *is*.

A mob's ``PhysicalMedia`` points here, and this is where a troubleshooting
session usually ends up: codec, raster, sample rate, and the locators that say
where the file was last seen.

The hierarchy below follows the class dictionary written in the reference
samples themselves (``MDTP -> MDES``, ``DIDD -> MDFL``, ``CDCI -> DIDD``,
``JPED -> CDCI``, ``MPGI -> CDCI``), not the OMF specification, where they
differ.  Classes the samples' schema declares but never instantiates are
included: they read as typed objects the moment a file uses them, and as
nothing at all until then.
"""
from __future__ import annotations

from typing import List, Optional

from .. import enums
from ..core import PropertyDef as P, register_class
from .base import OMFObject
from .locators import Locator

__all__ = [
    "MediaDescriptor", "TapeDescriptor", "FilmDescriptor", "NagraDescriptor",
    "FileDescriptor", "MultiDescriptor", "DigitalImageDescriptor",
    "CDCIDescriptor", "RGBADescriptor", "JPEGDescriptor", "MPEGDescriptor",
    "TIFFDescriptor", "DVDescriptor", "VideoDescriptor", "VC1Descriptor",
    "AudioDescriptor", "PCMADescriptor", "MPEGAudioDescriptor",
    "WAVEDescriptor", "AIFCDescriptor", "SoundDesignerDescriptor",
    "DataDescriptor", "ANCDataDescriptor", "VBIDataDescriptor", "Rect",
]


class Rect(object):
    """One of the ``DIDD`` rectangles, as four exact rationals.

    Avid stores each rectangle as eight properties -- an X, Y, width and
    height, each a separate numerator and denominator -- so the geometry
    survives non-integer scaling.  This groups them back up.
    """

    __slots__ = ("x", "y", "width", "height")

    def __init__(self, x, y, width, height):
        self.x, self.y, self.width, self.height = x, y, width, height

    def __eq__(self, other):
        return (isinstance(other, Rect) and (other.x, other.y, other.width, other.height)
                == (self.x, self.y, self.width, self.height))

    def __hash__(self):
        return hash((self.x, self.y, self.width, self.height))

    def __repr__(self):
        return "<Rect x=%s y=%s %sx%s>" % (self.x, self.y, self.width, self.height)


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
        P("acf_wchar", "OMFI:AMDL:acfWChar"),
        P("amdl_attributes", "OMFI:AMDL:Attributes", deref=True,
          doc="Avid's descriptor-level attribute list, distinct from CPNT:Attributes"),
        P("version", "OMFI:MDES:Version"),
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
class TapeDescriptor(MediaDescriptor):
    """``MDTP`` -- media that lives on a videotape.

    The class dictionary of both samples declares ``MDTP -> MDES``.  A tape
    descriptor carries no path, because there is no file: identity is the
    tape name on the mob and the timecode on its track.  Absent from both
    samples, whose media was imported and transcoded rather than captured.
    """

    class_id = "MDTP"
    __slots__ = ()
    propertydefs = [
        P("cframe", "OMFI:MDTP:CFrame",
          doc="meaning unverified -- the only MDTP property the schema declares"),
    ]

    def summary(self) -> str:
        return "tape"


@register_class
class FilmDescriptor(MediaDescriptor):
    """``MDFM`` -- media that lives on film stock.

    Declared in the schema of both samples; the schema gives it no properties
    of its own beyond the near-universal ``AMEVersion``, so everything useful
    sits on ``MDES`` and on the ``ECCP`` edge-code track.
    """

    class_id = "MDFM"
    __slots__ = ()

    def summary(self) -> str:
        return "film"


@register_class
class NagraDescriptor(MediaDescriptor):
    """``MDNG`` -- audio on a Nagra field recorder.

    Declared in the schema of both samples with no properties of its own.
    """

    class_id = "MDNG"
    __slots__ = ()

    def summary(self) -> str:
        return "nagra"


@register_class
class FileDescriptor(MediaDescriptor):
    """``MDFL`` -- media stored in a file: length, rate, and where it starts."""

    class_id = "MDFL"
    __slots__ = ()
    propertydefs = [
        P("length", "OMFI:MDFL:Length", doc="duration in sample_rate units"),
        P("sample_rate", "OMFI:MDFL:SampleRate"),
        P("data_offset", "OMFI:MDFL:dataOffset", doc="byte offset of essence in the file"),
        P("is_omfi", "OMFI:MDFL:IsOMFI",
          doc="true when the essence is wrapped in OMF rather than raw"),
        P("version", "OMFI:MDFL:Version"),
    ]

    def summary(self) -> str:
        return "%s %s, %s samples" % (self.mob_kind_name, self.sample_rate, self.length)


@register_class
class MultiDescriptor(FileDescriptor):
    """``MULD`` -- one file holding several essence streams.

    Used where a single media file carries, say, video plus interleaved audio:
    :attr:`descriptors` holds one child descriptor per stream.  Absent from
    both reference samples, where Avid writes one file per stream.
    """

    class_id = "MULD"
    __slots__ = ()
    propertydefs = [
        P("count", "OMFI:MULD:Count"),
        P("descriptors", "OMFI:MULD:Descriptor", deref=True, multi=True),
        P("descriptor_ids", "OMFI:MULD:DescriptorIDs"),
    ]

    def children(self) -> "List[MediaDescriptor]":
        """The per-stream descriptors, resolved."""
        refs = self.descriptors or []
        out = []
        for ref in refs:
            for one in (ref if isinstance(ref, list) else [ref]):
                if isinstance(one, MediaDescriptor):
                    out.append(one)
        return out

    def summary(self) -> str:
        kids = self.children()
        return "multi (%s)" % ", ".join(k.summary() for k in kids) if kids else "multi"


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
        P("video_line_map_size", "OMFI:DIDD:VideoLineMapSize"),
        P("stored_f2_offset", "OMFI:DIDD:StoredF2Offset",
          doc="offset of the second field when fields are stored separately"),
        P("frame_start_offset", "OMFI:DIDD:FrameStartOffset"),
        P("essence_element_size_kind", "OMFI:DIDD:EssenceElementSizeKind"),
        P("frame_sample_size_checked", "OMFI:DIDD:FrameSampleSizeHasBeenCheckedWithMapper"),
        P("reformatting_option", "OMFI:DIDD:ReformattingOption",
          enum=enums.REFORMATTING_OPTION),
        P("has_premultiplied_alpha", "OMFI:DIDD:HasPremultipliedAlpha"),
        P("needs_vertical_flip", "OMFI:DIDD:NeedsVerticalFlip"),
        P("next_descriptor", "OMFI:DIDD:NextDIDDesc", deref=True,
          doc="chains to an alternate-resolution descriptor for the same media"),
    ]

    #: The four exact-rational rectangles, in the order OMF defines them.
    #: Each is eight properties -- ``<name>XNum``/``XDen`` and so on -- which
    #: :meth:`rect` reassembles into a :class:`Rect`.
    RECTANGLES = ("Valid", "Essence", "Source", "Framing")

    structural_properties = tuple(
        "OMFI:DIDD:%s%s%s" % (rect, axis, half)
        for rect in RECTANGLES
        for axis in ("X", "Y", "Width", "Height")
        for half in ("Num", "Den"))

    def rect(self, name: str) -> Optional[Rect]:
        """One of the exact-rational rectangles, or ``None`` if absent.

        ``name`` is one of :attr:`RECTANGLES`.  Each component comes back as a
        ``(numerator, denominator)`` pair rather than a float, because that is
        what the file holds and rounding here would be lossy.
        """
        parts = []
        for axis in ("X", "Y", "Width", "Height"):
            num = self.get("OMFI:DIDD:%s%sNum" % (name, axis))
            den = self.get("OMFI:DIDD:%s%sDen" % (name, axis))
            parts.append(None if num is None and den is None else (num, den))
        if all(p is None for p in parts):
            return None
        return Rect(*parts)

    def rects(self) -> "dict":
        """Every rectangle the file wrote, keyed by name."""
        found = {}
        for name in self.RECTANGLES:
            r = self.rect(name)
            if r is not None:
                found[name.lower()] = r
        return found

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
class JPEGDescriptor(CDCIDescriptor):
    """``JPED`` -- Avid's motion-JPEG resolutions (AVR, JFIF).

    The class dictionary of both samples declares ``JPED -> CDCI``.  The
    quantisation tables are carried inline; ``JPEGTableID`` names a table Media
    Composer already knows, in which case they are omitted.
    """

    class_id = "JPED"
    __slots__ = ()
    propertydefs = [
        P("jpeg_table_id", "OMFI:JPED:JPEGTableID"),
        P("quantization_tables", "OMFI:JPED:QuantizationTables"),
        P("quantization_tables_length", "OMFI:JPED:QuantizationTables Length",
          doc="the space in the property name is Avid's, and is preserved"),
        P("image_start_alignment", "OMFI:JPED:ImageStartAlignment"),
    ]


@register_class
class MPEGDescriptor(CDCIDescriptor):
    """``MPGI`` -- long-GOP MPEG picture essence (XDCAM and friends).

    The class dictionary of both samples declares ``MPGI -> CDCI``.  Because
    the GOP means a frame is not independently decodable, the descriptor
    carries what a random-access seek needs: the GOP structure, the leading
    and trailing frames to discard, and a copy of the sequence header.
    """

    class_id = "MPGI"
    __slots__ = ()
    propertydefs = [
        P("mpeg_version", "OMFI:MPGI:MPEGVersion"),
        P("is_mpeg1", "OMFI:MPGI:isMPEG1"),
        P("stream_type", "OMFI:MPGI:StreamType"),
        P("profile_and_level", "OMFI:MPGI:ProfileAndLevel"),
        P("gop_structure", "OMFI:MPGI:GOPStructure"),
        P("min_gop_length", "OMFI:MPGI:omMPGIMinGOPLength"),
        P("max_gop_length", "OMFI:MPGI:omMPGIMaxGOPLength"),
        P("random_access", "OMFI:MPGI:RandomAccess"),
        P("leading_discard", "OMFI:MPGI:LeadingDiscard"),
        P("trailing_discard", "OMFI:MPGI:TrailingDiscard"),
        P("sequence_header", "OMFI:MPGI:SequenceHdr"),
        P("sequence_header_length", "OMFI:MPGI:SequenceHdrLen"),
        P("offset_to_frame_indexes", "OMFI:MPGI:OffsetToFrameIndexes"),
    ]


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
        P("pixel_layout_size", "OMFI:RGBA:PixelLayoutSize"),
        P("pixel_structure_size", "OMFI:RGBA:PixelStructureSize"),
        P("alpha_min_ref", "OMFI:RGBA:AlphaMinRef"),
        P("alpha_max_ref", "OMFI:RGBA:AlphaMaxRef"),
        P("palette", "OMFI:RGBA:Palette"),
        P("palette_size", "OMFI:RGBA:PaletteSize"),
        P("palette_layout", "OMFI:RGBA:PaletteLayout"),
        P("palette_layout_size", "OMFI:RGBA:PaletteLayoutSize"),
        P("palette_structure", "OMFI:RGBA:PaletteStructure"),
        P("palette_structure_size", "OMFI:RGBA:PaletteStructureSize"),
    ]


class AudioDescriptor(FileDescriptor):
    """The ``MDAU`` property group, shared by every audio descriptor.

    ``MDAU`` is not a class -- it never appears in the class dictionary and no
    object is ever tagged with it -- but it *is* a property namespace that
    ``PCMA``, ``MPGA``, ``WAVD``, ``AIFD`` and ``SD2D`` all draw on.  Binding
    it once here means ``descriptor.num_channels`` works whatever the wrapper,
    which is what a caller actually wants to ask.
    """

    __slots__ = ()
    propertydefs = [
        P("num_channels", "OMFI:MDAU:NumChannels"),
        P("number_of_channels", "OMFI:MDAU:NumberOfChannels",
          doc="the long spelling; Avid writes the short one"),
        P("number_of_samples", "OMFI:MDAU:NumberOfSamples"),
        P("bits_per_sample", "OMFI:MDAU:BitsPerSample"),
        P("bytes_per_sample", "OMFI:MDAU:BytesPerSample"),
        P("mdau_sampling_rate", "OMFI:MDAU:AudioSamplingRate"),
        P("mdau_coding_format", "OMFI:MDAU:AudioCodingFormat"),
        P("mdau_ref_level", "OMFI:MDAU:AudioRefLevel"),
        P("mdau_dial_norm", "OMFI:MDAU:DialNorm"),
        P("mdau_electro_spatial_formulation", "OMFI:MDAU:ElectroSpatialFormulation"),
        P("mdau_locked", "OMFI:MDAU:Locked"),
        P("clock_rate", "OMFI:MDAU:ClockRate"),
        P("clock_divisor", "OMFI:MDAU:ClockDivisor"),
        P("pull_down", "OMFI:MDAU:PullDown"),
    ]

    @property
    def sampling_rate(self):
        """The audio sample rate, whichever spelling the wrapper used."""
        for name in ("OMFI:PCMA:AudioSamplingRate", "OMFI:MDAU:AudioSamplingRate",
                     "OMFI:MDFL:SampleRate"):
            value = self.get(name)
            if value is not None:
                return value
        return None

    def summary(self) -> str:
        rate = self.sampling_rate
        bits = []
        if rate:
            bits.append("%gkHz" % (float(rate) / 1000.0))
        if self.bits_per_sample:
            bits.append("%d-bit" % self.bits_per_sample)
        if self.num_channels:
            bits.append("%dch" % self.num_channels)
        return " ".join(bits) or self.mob_kind_name


@register_class
class PCMADescriptor(AudioDescriptor):
    """``PCMA`` -- linear PCM audio, with BWF peak-envelope metadata.

    This is what Avid writes for the ``.mxf`` audio it manages itself, and it
    is the only audio descriptor present in either reference sample.
    """

    class_id = "PCMA"
    __slots__ = ()
    propertydefs = [
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
        P("peak_envelope_data", "OMFI:PCMA:PeakEnvelopeData"),
        P("subframe_alignment", "OMFI:PCMA:SubframeAlignment"),
        P("smpte_ebu_timestamp", "OMFI:PCMA:SmpteEbuTimestamp"),
        P("timecode_frame_rate", "OMFI:PCMA:TimecodeFrameRate"),
    ]


@register_class
class MPEGAudioDescriptor(AudioDescriptor):
    """``MPGA`` -- MPEG audio (layer II / III).

    Everything about the sound itself is in the shared ``MDAU`` group; what
    ``MPGA`` adds is what a decoder needs to find a frame boundary.
    """

    class_id = "MPGA"
    __slots__ = ()
    propertydefs = [
        P("bit_rate", "OMFI:MPGA:BitRate"),
        P("subframe_alignment", "OMFI:MPGA:SubframeAlignment"),
        P("origin", "OMFI:MPGA:Origin"),
        P("version", "OMFI:MPGA:Version"),
    ]


@register_class
class WAVEDescriptor(AudioDescriptor):
    """``WAVD`` -- a Broadcast WAVE file.

    ``Summary`` holds the file's own RIFF chunks verbatim, which is where the
    originator, the ``bext`` timestamp and the channel layout live -- Avid
    keeps the header rather than re-describing it.

    Note the class split, which pyavb does not make: in OMF the *descriptor*
    is ``WAVD`` and the *media data* is ``WAVE`` (:class:`~mdb.objects.media.WAVEData`).
    pyavb folds them together under ``WAVE`` because the AVB container does;
    the MDB schema declares both names separately, so both are bound here.
    """

    class_id = "WAVD"
    __slots__ = ()
    propertydefs = [
        P("summary", "OMFI:WAVD:Summary", doc="the source file's RIFF chunks, verbatim"),
        P("version", "OMFI:WAVD:Version"),
    ]


@register_class
class AIFCDescriptor(AudioDescriptor):
    """``AIFD`` -- an AIFF-C file.  The AIFF twin of :class:`WAVEDescriptor`."""

    class_id = "AIFD"
    __slots__ = ()
    propertydefs = [
        P("summary", "OMFI:AIFD:Summary", doc="the source file's AIFF chunks, verbatim"),
        P("data_pos", "OMFI:AIFD:MC:DataPos", doc="byte offset of the SSND payload"),
        P("version", "OMFI:AIFD:Version"),
    ]


@register_class
class SoundDesignerDescriptor(AudioDescriptor):
    """``SD2D`` -- Sound Designer II, the Pro Tools legacy format.

    Unusually, the schema gives this one both descriptor properties and a
    ``Data``/``MobID`` pair, so it doubles as its own media-data class.
    """

    class_id = "SD2D"
    __slots__ = ()
    propertydefs = [
        P("sd2_num_channels", "OMFI:SD2D:NumChannels"),
        P("sd2_bits_per_sample", "OMFI:SD2D:BitsPerSample"),
        P("data", "OMFI:SD2D:Data"),
        P("mob_id", "OMFI:SD2D:MobID"),
    ]


# --------------------------------------------------------------------------
# the remaining picture descriptors
# --------------------------------------------------------------------------
@register_class
class TIFFDescriptor(DigitalImageDescriptor):
    """``TIFD`` -- TIFF stills and the older Avid TIFF-wrapped resolutions.

    ``IsContiguous`` and ``IsUniform`` are the pair that decides whether a
    frame can be found by arithmetic or needs the frame index.
    """

    class_id = "TIFD"
    __slots__ = ()
    propertydefs = [
        P("is_uniform", "OMFI:TIFD:IsUniform", doc="every frame the same size"),
        P("is_contiguous", "OMFI:TIFD:IsContiguous", doc="frames stored back to back"),
        P("leading_lines", "OMFI:TIFD:LeadingLines"),
        P("trailing_lines", "OMFI:TIFD:TrailingLines"),
        P("jpeg_table_id", "OMFI:TIFD:JPEGTableID"),
        P("first_ifd", "OMFI:TIFD:FirstIFD", doc="offset of the first image file directory"),
        P("summary", "OMFI:TIFD:Summary"),
        P("buf_len", "OMFI:TIFD:BufLen"),
        P("rle_desc", "OMFI:TIFD:RLEDesc"),
        P("uncomp_desc", "OMFI:TIFD:UncompDesc"),
        P("tiff_uniformness", "OMFI:TIFD:Uniformness"),
        P("version", "OMFI:TIFD:Version"),
    ]


@register_class
class DVDescriptor(DigitalImageDescriptor):
    """``DVRD`` -- DV / DVCPRO essence.

    Property names carry Avid's Hungarian ``l`` prefix, which is preserved on
    the OMF side and dropped on the Python side.
    """

    class_id = "DVRD"
    __slots__ = ()
    propertydefs = [
        P("dv_id", "OMFI:DVRD:szID"),
        P("dv_version", "OMFI:DVRD:lVersion"),
        P("data_offset", "OMFI:DVRD:lDataOffset"),
        P("index_offset", "OMFI:DVRD:lIndexOffset"),
        P("data_rate", "OMFI:DVRD:lDataRate"),
        P("field_count", "OMFI:DVRD:lFieldCount"),
        P("is_pal", "OMFI:DVRD:lPAL"),
        P("q_factor", "OMFI:DVRD:lQFactor"),
        P("dyna_q", "OMFI:DVRD:lDynaQ"),
        P("x_extent", "OMFI:DVRD:lXExtent"),
        P("y_extent", "OMFI:DVRD:lYExtent"),
    ]


@register_class
class VideoDescriptor(DigitalImageDescriptor):
    """``MDVI`` -- Avid's own video-media descriptor.

    Predates the OMF ``DIDD`` raster model and describes the capture hardware's
    view of the signal: which lines were captured, in what format, with what
    mask.  Absent from both reference samples.
    """

    class_id = "MDVI"
    __slots__ = ()
    propertydefs = [
        P("width", "OMFI:MDVI:Width"),
        P("height", "OMFI:MDVI:Height"),
        P("fields", "OMFI:MDVI:Fields"),
        P("video_format", "OMFI:MDVI:VideoFormat"),
        P("source_format", "OMFI:MDVI:SourceFormat"),
        P("capture_mask", "OMFI:MDVI:CaptureMask"),
        P("capture_shift", "OMFI:MDVI:CaptureShift"),
        P("uniform", "OMFI:MDVI:Uniform"),
        P("vc_id", "OMFI:MDVI:TypevcID"),
        P("video_modifier", "OMFI:MDVI:TypeVideoModifier"),
    ]


@register_class
class VC1Descriptor(DigitalImageDescriptor):
    """``VC1D`` -- SMPTE VC-1 (Windows Media) picture essence."""

    class_id = "VC1D"
    __slots__ = ()
    propertydefs = [
        P("profile", "OMFI:VC1D:Profile"),
        P("level", "OMFI:VC1D:Level"),
        P("average_bit_rate", "OMFI:VC1D:AverageBitRate"),
        P("max_bit_rate", "OMFI:VC1D:MaxBitRate"),
        P("max_gop", "OMFI:VC1D:MaxGOP"),
        P("b_picture_count", "OMFI:VC1D:BPictureCount"),
        P("identical_gop", "OMFI:VC1D:IdenticalGOP"),
        P("single_sequence", "OMFI:VC1D:SingleSequence"),
        P("coded_content_scanning", "OMFI:VC1D:CodedContentScanning"),
        P("initialization_metadata", "OMFI:VC1D:InitializationMetadata"),
    ]


# --------------------------------------------------------------------------
# data essence
# --------------------------------------------------------------------------
@register_class
class DataDescriptor(FileDescriptor):
    """``DATD`` -- essence that is neither picture nor sound.

    The frame-index properties are the same shape as ``DIDD``'s, because the
    problem is the same: a file of variable-size samples needs an index to be
    seekable.
    """

    class_id = "DATD"
    __slots__ = ()
    propertydefs = [
        P("is_filler", "OMFI:DATD:IsFiller"),
        P("min_sample_size", "OMFI:DATD:MinSampleSize"),
        P("max_sample_size", "OMFI:DATD:MaxSampleSize"),
        P("first_frame_offset", "OMFI:DATD:FirstFrameOffset"),
        P("offset_to_frame_indexes", "OMFI:DATD:OffsetToFrameIndexes"),
        P("offset_to_frame_indexes_valid", "OMFI:DATD:IsOffsetToFrameIndexesValid"),
    ]

    def summary(self) -> str:
        return "data"


@register_class
class ANCDataDescriptor(DataDescriptor):
    """``ANCD`` -- SMPTE 291 ancillary data: captions, AFD, timecode packets.

    The manifest lists which DIDs and SDIDs the stream carries, so a caller can
    tell a caption track from a metadata track without decoding it.
    """

    class_id = "ANCD"
    __slots__ = ()
    propertydefs = [
        P("manifest", "OMFI:ANCD:ManifestArray"),
        P("manifest_element_count", "OMFI:ANCD:ManifestElementCount"),
    ]

    def summary(self) -> str:
        return "ancillary data"


@register_class
class VBIDataDescriptor(DataDescriptor):
    """``VBID`` -- vertical-blanking-interval data, the analogue-era twin of
    :class:`ANCDataDescriptor`."""

    class_id = "VBID"
    __slots__ = ()
    propertydefs = [
        P("manifest", "OMFI:VBID:ManifestArray"),
        P("manifest_element_count", "OMFI:VBID:ManifestElementCount"),
    ]

    def summary(self) -> str:
        return "VBI data"
