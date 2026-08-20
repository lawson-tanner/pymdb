"""Effects: the ``TRKG`` descendants that transform their tracks.

None of these appears in either reference sample, and that is the expected
result rather than a gap -- an effect lives in the ``.avb`` bin, and only its
*rendered* media reaches the MDB, as an ordinary mob with an ordinary
descriptor.  They are defined here because the class dictionary of both
samples declares them, so a file that does carry one (a precompute written
back into the media folder, or a future Media Composer that indexes more)
reads as a typed object rather than as a bag of properties.

The inheritance below is the one the samples' own class dictionary states::

    TRKG -> TKFX -> PVOL
                 -> EQMB
                 -> ASPI
    TRKG -> WARP -> STRB
    TRAN -> TNFX

which differs from pyavb's AVB reading in one place: pyavb makes ``MASK``,
``SPED`` and ``REPT`` ``WARP`` subclasses, and the MDB dictionary declares
only ``STRB``.  The others are still modelled as time warps here, with this
note, because the property sets agree and nothing dispatches on it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core import PropertyDef as P, register_class
from .base import OMFObject
from .trackgroups import TrackGroup

__all__ = ["TrackEffect", "PanVolumeEffect", "AudioSuitePluginEffect",
           "EqualizerMultiBand", "EqualizerBand", "TimeWarp", "CaptureMask",
           "StrobeEffect", "MotionEffect", "Repeat", "Transition",
           "TransitionEffect", "InlineEqualizerBand"]


@register_class
class TrackEffect(TrackGroup):
    """``TKFX`` -- the base for every rendered track effect.

    The ``GlobalInfo`` block is spelled with a ``TNFX`` prefix even on a
    ``TKFX`` object, because the two classes share the structure and Avid
    named the properties after the first class to use them.  Both spellings
    are bound.
    """

    class_id = "TKFX"
    __slots__ = ()
    propertydefs = [
        P("left_length", "OMFI:TKFX:MC:LeftLength"),
        P("right_length", "OMFI:TKFX:MC:RightLength"),
        P("keyframes", "OMFI:TKFX:MC:KeyFrameList", deref=True),
        P("trackman", "OMFI:TKFX:MC:TrackMan", deref=True, doc="the TKMN tracker manager"),
        P("force_software", "OMFI:TKFX:MC:ForceSoftware"),
        P("never_hardware", "OMFI:TKFX:MC:NeverHardware"),
        P("global_info", "OMFI:TKFX:MC:GlobalInfo"),
        P("global_info_version", "OMFI:TKFX:MC:GlobalInfoVersion"),
        # the TNFX spellings of the same block
        P("info_version", "OMFI:TNFX:MC:GlobalInfoVersion"),
        P("info_minor_version", "OMFI:TNFX:MC:GlobalInfoMinorVersion"),
        P("info_current", "OMFI:TNFX:MC:GlobalInfo.kfCurrent"),
        P("info_smooth", "OMFI:TNFX:MC:GlobalInfo.kfSmooth"),
        P("info_color_item", "OMFI:TNFX:MC:GlobalInfo.colorItem"),
        P("info_quality", "OMFI:TNFX:MC:GlobalInfo.quality"),
        P("info_is_reversed", "OMFI:TNFX:MC:GlobalInfo.isReversed"),
        P("info_aspect_on", "OMFI:TNFX:MC:GlobalInfo.aspectOn"),
        P("info_unique_id_1", "OMFI:TNFX:MC:GlobalInfo.UniqueId1"),
        P("info_unique_id_2", "OMFI:TNFX:MC:GlobalInfo.UniqueId2"),
    ]

    def _repr_extra(self):
        return repr(self.effect_id) if self.effect_id else ""


@register_class
class PanVolumeEffect(TrackEffect):
    """``PVOL`` -- audio level and pan.

    ``Level`` and ``Pan`` are fixed-point integers, not dB and not a -1..1
    float; :attr:`level_db` converts, and returns ``None`` at silence rather
    than negative infinity.
    """

    class_id = "PVOL"
    __slots__ = ()
    propertydefs = [
        P("level", "OMFI:PVOL:MC:Level"),
        P("level_ex", "OMFI:PVOL:MC:LevelEx"),
        P("pan", "OMFI:PVOL:MC:Pan"),
        P("level_set", "OMFI:PVOL:MC:LevelSet"),
        P("pan_set", "OMFI:PVOL:MC:PanSet"),
        P("suppress_validation", "OMFI:PVOL:MC:SuppressValidation"),
        P("supports_separate_gain", "OMFI:PVOL:MC:DoesSuprtSeprtClipG",
          doc="spelled 'DoesSuprtSeprtClipG' in the schema -- Avid's abbreviation, preserved"),
        P("is_trim_gain_effect", "OMFI:PVOL:MC:IsTrimGainEffect"),
    ]

    #: ``Level`` is stored as a fixed-point fraction of unity gain.
    UNITY_LEVEL = 0x10000

    @property
    def level_db(self) -> Optional[float]:
        """:attr:`level` as decibels relative to unity gain.

        ``None`` when the level is unset or zero -- silence has no dB value,
        and returning ``-inf`` would poison any arithmetic downstream.
        """
        import math
        level = self.level
        if not level or level <= 0:
            return None
        return 20.0 * math.log10(float(level) / self.UNITY_LEVEL)

    def _repr_extra(self):
        db = self.level_db
        return "level=%s%s pan=%s" % (
            self.level, "" if db is None else " (%.1f dB)" % db, self.pan)


@register_class
class EqualizerBand(OMFObject):
    """``EQBD`` -- one band of an :class:`EqualizerMultiBand`.

    Declared as a class in the dictionary of both samples, so in a Bento
    container the bands are most likely separate objects reached through
    ``EQMB:AV:Bands``.  pyavb reads them inline instead, because the AVB byte
    stream writes them that way -- so :meth:`EqualizerMultiBand.bands` handles
    both shapes and this class covers the object one.
    """

    class_id = "EQBD"
    __slots__ = ()
    propertydefs = [
        P("type", "OMFI:EQBD:AV:BandType"),
        P("freq", "OMFI:EQBD:AV:BandFreq"),
        P("gain", "OMFI:EQBD:AV:BandGain"),
        P("q", "OMFI:EQBD:AV:BandQ"),
        P("enable", "OMFI:EQBD:AV:BandEnable"),
    ]

    def _repr_extra(self):
        return "%sHz gain=%s q=%s%s" % (self.freq, self.gain, self.q,
                                        "" if self.enable else " (off)")


class InlineEqualizerBand(object):
    """A band read from the flat, inline form.

    Used when ``EQMB:AV:Bands`` holds no object references and the five band
    properties are written directly on the parent, one repetition per band.
    Duck-type compatible with :class:`EqualizerBand` for the five values.
    """

    __slots__ = ("type", "freq", "gain", "q", "enable")

    def __init__(self, type=None, freq=None, gain=None, q=None, enable=None):
        self.type, self.freq, self.gain = type, freq, gain
        self.q, self.enable = q, enable

    def _state(self):
        return tuple(getattr(self, s) for s in self.__slots__)

    def __eq__(self, other):
        return isinstance(other, InlineEqualizerBand) and self._state() == other._state()

    def __hash__(self):
        return hash(self._state())

    def __repr__(self):
        return "<InlineEqualizerBand %sHz gain=%s q=%s%s>" % (
            self.freq, self.gain, self.q, "" if self.enable else " (off)")


@register_class
class EqualizerMultiBand(TrackEffect):
    """``EQMB`` -- the multi-band audio EQ."""

    class_id = "EQMB"
    __slots__ = ()
    propertydefs = [
        P("num_bands", "OMFI:EQMB:AV:NumBands"),
        P("band_refs", "OMFI:EQMB:AV:Bands", deref=True),
        P("effect_enable", "OMFI:EQMB:AV:EffectEnable"),
        P("filter_name", "OMFI:EQMB:AV:FilterName"),
        P("suppress_validation", "OMFI:EQMB:AV:SuppressValidation"),
    ]

    _BAND_PROPERTIES = (
        ("type", "OMFI:EQBD:AV:BandType"),
        ("freq", "OMFI:EQBD:AV:BandFreq"),
        ("gain", "OMFI:EQBD:AV:BandGain"),
        ("q", "OMFI:EQBD:AV:BandQ"),
        ("enable", "OMFI:EQBD:AV:BandEnable"),
    )

    def bands(self) -> list:
        """The EQ bands, whichever way the file wrote them.

        Prefers real ``EQBD`` objects from ``EQMB:AV:Bands``; falls back to the
        inline form, where the five band properties are repeated on this object
        once per band and a band is assembled by index.
        """
        refs = self.band_refs
        if refs is not None:
            if not isinstance(refs, list):
                refs = [refs]
            found = [r for r in refs if isinstance(r, EqualizerBand)]
            if found:
                return found
        columns = {name: self.values(omf) for name, omf in self._BAND_PROPERTIES}
        count = max((len(v) for v in columns.values()), default=0)
        return [InlineEqualizerBand(**{name: values[i]
                                       for name, values in columns.items()
                                       if i < len(values)})
                for i in range(count)]

    def _repr_extra(self):
        return "%r, %d bands" % (self.filter_name, len(self.bands()))


@register_class
class AudioSuitePluginEffect(TrackEffect):
    """``ASPI`` -- a rendered AudioSuite (Pro Tools) plug-in.

    The plug-in's own state is opaque: :attr:`bag_of_bits` and the per-chunk
    ``chunkfData`` are the plug-in's private format, and are exposed as bytes
    without interpretation.

    Two of this class's property IDs collide with ``FXPS``'s in the schema of
    both samples (``ASPI:tracksToAffect`` with ``FXPS:ccNumParams``, and
    ``ASPI:renderingMode`` with ``FXPS:colorCorrection``).  Both bindings are
    kept by the container; ``mdb validate`` reports the collision.
    """

    class_id = "ASPI"
    __slots__ = ()
    propertydefs = [
        P("num_plugins", "OMFI:ASPI:numOfPlugIns"),
        P("plugin_refs", "OMFI:ASPI:omfiAudioSuitePlugIn", deref=True, multi=True),
        P("plugin_name", "OMFI:ASPI:plugInName", multi=True),
        P("manufacturer_id", "OMFI:ASPI:plugInfManufacturerID", multi=True),
        P("product_id", "OMFI:ASPI:plugInfProductID", multi=True),
        P("plugin_id", "OMFI:ASPI:plugInfPlugInID", multi=True),
        P("num_chunks", "OMFI:ASPI:plugInNumOfChunks", multi=True),
        P("source_mob_id", "OMFI:ASPI:sourceMasterClipMobID"),
        P("mark_in", "OMFI:ASPI:markInForSourceMasterClip"),
        P("mark_out", "OMFI:ASPI:markOutForSourceMasterClip"),
        P("tracks_to_affect", "OMFI:ASPI:tracksToAffect"),
        P("rendering_mode", "OMFI:ASPI:renderingMode"),
        P("padding_secs", "OMFI:ASPI:paddingSecs"),
        P("preset_path", "OMFI:ASPI:presetPath"),
        P("preset_path_length", "OMFI:ASPI:presetPathLength"),
        P("bag_of_bits", "OMFI:ASPI:BagOfBits", doc="the plug-in's private state"),
    ]

    _CHUNK_PROPERTIES = (
        ("chunk_id", "OMFI:ASPI:chunkfChunkID"),
        ("name", "OMFI:ASPI:chunkfChunkName"),
        ("version", "OMFI:ASPI:chunkfVersion"),
        ("data", "OMFI:ASPI:chunkfData"),
        ("data_size", "OMFI:ASPI:chunkfDataSize"),
    )

    structural_properties = tuple(omf for _, omf in _CHUNK_PROPERTIES)

    def chunks(self) -> List[Dict[str, Any]]:
        """The plug-in's settings chunks, assembled from parallel properties."""
        columns = {name: self.values(omf) for name, omf in self._CHUNK_PROPERTIES}
        count = max((len(v) for v in columns.values()), default=0)
        return [{name: values[i] for name, values in columns.items() if i < len(values)}
                for i in range(count)]

    def _repr_extra(self):
        names = self.plugin_name or []
        return ", ".join(str(n) for n in names)


# --------------------------------------------------------------------------
# time warps
# --------------------------------------------------------------------------
@register_class
class TimeWarp(TrackGroup):
    """``WARP`` -- the base for effects that change the rate of time."""

    class_id = "WARP"
    __slots__ = ()
    propertydefs = [
        P("phase_offset", "OMFI:WARP:PhaseOffset"),
        P("warp_edit_rate", "OMFI:WARP:EditRate"),
        P("version", "OMFI:WARP:Version"),
    ]


@register_class
class StrobeEffect(TimeWarp):
    """``STRB`` -- hold every *n*-th frame.  ``STRB -> WARP`` in the class
    dictionary of both samples."""

    class_id = "STRB"
    __slots__ = ()
    propertydefs = [P("strobe_value", "OMFI:STRB:MC:StrobeVal", doc="frames held per step")]

    def _repr_extra(self):
        return "every %s" % self.strobe_value


@register_class
class MotionEffect(TimeWarp):
    """``SPED`` -- a speed change.

    The ratio is a plain numerator over denominator: 2/1 is double speed, 1/2
    is half.  Three of its four properties are misspelled ``OMIF`` rather than
    ``OMFI`` in the schema of both samples -- Avid's typo, and it is bound as
    written because that is what the file says.
    """

    class_id = "SPED"
    __slots__ = ()
    propertydefs = [
        P("numerator", "OMFI:SPED:Numerator"),
        P("denominator", "OMFI:SPED:Denominator"),
        P("version", "OMFI:SPED:Version"),
        P("offset_adjust", "OMIF:SPED:OffsetAdjust",
          doc="'OMIF' is the schema's spelling -- Avid's typo, preserved"),
        P("source_param_list", "OMIF:SPED:SourceParamList", deref=True),
        P("new_source_calculation", "OMIF:SPED:NewSourceCalculation"),
    ]

    @property
    def speed(self) -> Optional[float]:
        """The speed ratio as a float, or ``None`` if it is not set."""
        num, den = self.numerator, self.denominator
        if num is None or not den:
            return None
        return float(num) / float(den)

    def _repr_extra(self):
        speed = self.speed
        return "" if speed is None else "%g%%" % (speed * 100.0)


@register_class
class CaptureMask(TimeWarp):
    """``MASK`` -- the field-dropping mask used by film-to-video pulldown.

    Declared in neither sample's class dictionary; modelled as a time warp on
    pyavb's reading of the AVB container, where ``MASK -> WARP``.
    """

    class_id = "MASK"
    __slots__ = ()
    propertydefs = [
        P("is_double", "OMFI:MASK:IsDouble"),
        P("mask_bits", "OMFI:MASK:MaskBits", doc="one bit per field in the cadence"),
        P("version", "OMFI:MASK:Version"),
    ]


@register_class
class Repeat(TimeWarp):
    """``REPT`` -- loop the tracks below.

    Carries no properties of its own beyond version stamps: the repeat count
    falls out of the group length against the source length.
    """

    class_id = "REPT"
    __slots__ = ()
    propertydefs = [P("version", "OMFI:REPT:Version")]


# --------------------------------------------------------------------------
# transitions
# --------------------------------------------------------------------------
@register_class
class Transition(TrackGroup):
    """``TRAN`` -- a transition between two adjacent components.

    :attr:`cut_point` is where the cut would have been without the transition,
    which is what a conform needs in order to place it.
    """

    class_id = "TRAN"
    __slots__ = ()
    propertydefs = [
        P("cut_point", "OMFI:TRAN:CutPoint"),
        P("version", "OMFI:TRAN:Version"),
    ]

    def _repr_extra(self):
        return "cut=%s" % self.cut_point


@register_class
class TransitionEffect(Transition):
    """``TNFX`` -- a transition realised by an effect (a dissolve, a wipe).

    ``TNFX -> TRAN`` in the class dictionary of both samples.  Everything past
    the cut point is the same ``GlobalInfo`` block ``TKFX`` carries, which is
    why the property names below share the ``TNFX`` prefix with it.
    """

    class_id = "TNFX"
    __slots__ = ()
    propertydefs = [
        P("left_length", "OMFI:TNFX:MC:LeftLength"),
        P("right_length", "OMFI:TNFX:MC:RightLength"),
        P("keyframes", "OMFI:TNFX:MC:KeyFrameList", deref=True),
        P("trackman", "OMFI:TNFX:MC:TrackMan", deref=True),
        P("force_software", "OMFI:TNFX:MC:ForceSoftware"),
        P("never_hardware", "OMFI:TNFX:MC:NeverHardware"),
        P("global_info", "OMFI:TNFX:MC:GlobalInfo"),
        P("info_version", "OMFI:TNFX:MC:GlobalInfoVersion"),
        P("info_minor_version", "OMFI:TNFX:MC:GlobalInfoMinorVersion"),
        P("info_current", "OMFI:TNFX:MC:GlobalInfo.kfCurrent"),
        P("info_smooth", "OMFI:TNFX:MC:GlobalInfo.kfSmooth"),
        P("info_color_item", "OMFI:TNFX:MC:GlobalInfo.colorItem"),
        P("info_quality", "OMFI:TNFX:MC:GlobalInfo.quality"),
        P("info_is_reversed", "OMFI:TNFX:MC:GlobalInfo.isReversed"),
        P("info_aspect_on", "OMFI:TNFX:MC:GlobalInfo.aspectOn"),
        P("info_unique_id_1", "OMFI:TNFX:MC:GlobalInfo.UniqueId1"),
        P("info_unique_id_2", "OMFI:TNFX:MC:GlobalInfo.UniqueId2"),
    ]

    def _repr_extra(self):
        return "%s cut=%s" % (self.effect_id or "", self.cut_point)
