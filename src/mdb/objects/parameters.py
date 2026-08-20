"""Effect parameters: ``PRIT``, ``PRLS``, ``AVUP``, ``FXPS``, ``GRFX``.

A modern Avid effect keeps its settings as a ``PRLS`` list of ``PRIT``
parameters, each identified by a GUID rather than by name, so the same
parameter survives being renamed in the UI.  ``FXPS`` is the older, flat form:
one record per keyframe with every possible field present, which is why its
property list is forty-odd entries long and mostly empty in any given file.

None of these appears in either reference sample.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import enums
from ..core import PropertyDef as P, register_class
from .base import OMFObject
from .misc import SortedList

__all__ = ["ParameterItem", "ParameterList", "UserParameter", "EffectParamList",
           "GraphicEffect", "ColorCorrection"]


@register_class
class ParameterItem(OMFObject):
    """``PRIT`` -- one effect parameter.

    Identified by :attr:`uuid`, not by name: :attr:`name` is a display label
    and may be absent or localised.  A parameter that animates has no single
    value -- :attr:`control_track` points at the ``PRCL`` curve instead, and
    :attr:`multiple_value` says so.
    """

    class_id = "PRIT"
    __slots__ = ()
    propertydefs = [
        P("uuid", "OMFI:PRIT:GUID", doc="the parameter's stable identity"),
        P("name", "OMFI:PRIT:Name", doc="display label; identity lives in the GUID"),
        P("value", "OMFI:PRIT:Value"),
        P("value_type", "OMFI:PRIT:ValueType", enum=enums.PARAM_VALUE_TYPE),
        P("enabled", "OMFI:PRIT:Enabled"),
        P("multiple_value", "OMFI:PRIT:MultipleValue", doc="true when the parameter animates"),
        P("control_track", "OMFI:PRIT:ControlTrack", deref=True,
          doc="the PRCL curve, when the parameter animates"),
        P("contributes_to_signature", "OMFI:PRIT:ContributesToSignature",
          doc="whether this parameter is hashed into the effect's render signature"),
        P("id_high", "OMFI:PRIT:IDHigh"),
        P("id_low", "OMFI:PRIT:IDLow"),
    ]

    @property
    def id(self) -> Optional[int]:
        hi, lo = self.id_high, self.id_low
        if hi is None or lo is None:
            return None
        return ((hi & 0xFFFFFFFF) << 32) | (lo & 0xFFFFFFFF)

    def _repr_extra(self):
        return "%s=%s" % (self.name or self.uuid, self.value)


@register_class
class ParameterList(OMFObject):
    """``PRLS`` -- the list of ``PRIT`` parameters belonging to one effect."""

    class_id = "PRLS"
    __slots__ = ()
    propertydefs = [
        P("param_refs", "OMFI:PRLS:ParamItems", deref=True),
        P("num_items", "OMFI:PRLS:NumItems"),
    ]

    def parameters(self) -> "List[ParameterItem]":
        refs = self.param_refs
        if refs is None:
            return []
        if not isinstance(refs, list):
            refs = [refs]
        return [r for r in refs if isinstance(r, ParameterItem)]

    def __iter__(self):
        return iter(self.parameters())

    def __len__(self):
        return len(self.get("OMFI:PRLS:ParamItems") or [])

    def to_dict(self, deref: bool = False) -> Dict[str, Any]:
        """``{name or GUID: value}`` -- the flat view of an effect's settings."""
        if not deref:
            return super().to_dict()
        return {str(p.name or p.uuid): p.value for p in self.parameters()}

    def _repr_extra(self):
        return "%d parameters" % len(self)


@register_class
class UserParameter(OMFObject):
    """``AVUP`` -- a CoreFoundation-typed user parameter.

    The payload is opaque bytes plus a type GUID and its own byte order, which
    is how Avid round-trips plug-in settings whose structure it does not know.
    """

    class_id = "AVUP"
    __slots__ = ()
    propertydefs = [
        P("byte_order", "OMFI:AVUP:ByteOrder", doc="the payload's own endianness"),
        P("type_id", "OMFI:AVUP:TypeID"),
        P("data", "OMFI:AVUP:ValueData"),
        P("data_size", "OMFI:AVUP:ValueDataSize"),
    ]


@register_class
class EffectParamList(SortedList):
    """``FXPS`` -- the older, flat keyframe list.

    ``FXPS -> SMLS`` in the class dictionary of both samples, so the keyframes
    themselves are a fixed-stride blob reachable through
    :meth:`~mdb.objects.misc.SortedList.records`.  The named properties below
    are the per-keyframe fields, written once per keyframe; they are declared
    ``multi`` so ``obj.pos_x`` gives the whole track rather than just the last
    value.
    """

    class_id = "FXPS"
    __slots__ = ()
    propertydefs = [
        P("original_length", "OMFI:FXPS:originalLength"),
        P("window_offset", "OMFI:FXPS:omFXwindowOffset"),
        P("keyframe_size", "OMFI:FXPS:keyFrameSize"),
        P("num_keyframes", "OMFI:FXPS:numKeyFrames"),
        P("attr_list", "OMFI:FXPS:attrList", deref=True),
        P("attr_effect_id", "OMFI:FXPS:attrEffectID"),
        P("attr_effect_id_len", "OMFI:FXPS:attrEffectIDLen"),
        P("percent_time", "OMFI:FXPS:percentTime", multi=True),
        P("level", "OMFI:FXPS:level", multi=True),
        P("selected", "OMFI:FXPS:selected", multi=True),
        P("enable_key_flags", "OMFI:FXPS:enableKeyFlags", multi=True),
        P("pos_x", "OMFI:FXPS:posX", multi=True),
        P("pos_y", "OMFI:FXPS:posY", multi=True),
        P("floor_x", "OMFI:FXPS:xFloor", multi=True),
        P("ceil_x", "OMFI:FXPS:xCeiling", multi=True),
        P("floor_y", "OMFI:FXPS:yFloor", multi=True),
        P("ceil_y", "OMFI:FXPS:yCeiling", multi=True),
        P("scale_x", "OMFI:FXPS:xScale", multi=True),
        P("scale_y", "OMFI:FXPS:yScale", multi=True),
        P("crop_left", "OMFI:FXPS:cropLeft", multi=True),
        P("crop_right", "OMFI:FXPS:cropRight", multi=True),
        P("crop_top", "OMFI:FXPS:cropTop", multi=True),
        P("crop_bottom", "OMFI:FXPS:cropBottom", multi=True),
        P("box_left", "OMFI:FXPS:boxLeft", multi=True),
        P("box_right", "OMFI:FXPS:boxRight", multi=True),
        P("box_top", "OMFI:FXPS:boxTop", multi=True),
        P("box_bottom", "OMFI:FXPS:boxBottom", multi=True),
        P("box_x_scale", "OMFI:FXPS:boxLvl2Xscale", multi=True),
        P("box_y_scale", "OMFI:FXPS:boxLvl2Yscale", multi=True),
        P("box_x_pos", "OMFI:FXPS:FXboxLvl2Xpos", multi=True),
        P("box_y_pos", "OMFI:FXPS:omFXboxLvl2Ypos", multi=True),
        P("border_width", "OMFI:FXPS:borderWidth", multi=True),
        P("border_soft", "OMFI:FXPS:borderSoft", multi=True),
        P("spill_gain", "OMFI:FXPS:spillGain", multi=True),
        P("spill_gain_2", "OMFI:FXPS:spillSecondGain", multi=True),
        P("spill_soft", "OMFI:FXPS:spillSoft", multi=True),
        P("spill_soft_2", "OMFI:FXPS:spillSecondSoft", multi=True),
        P("colors", "OMFI:FXPS:colors", multi=True),
        P("num_colors", "OMFI:FXPS:nColors"),
        P("user_param", "OMFI:FXPS:userParam", multi=True),
        P("user_param_size", "OMFI:FXPS:userParamSize", multi=True),
        # shares a property ID with ASPI:renderingMode / ASPI:ccNumParams --
        # see AudioSuitePluginEffect for the collision
        P("color_correction", "OMFI:FXPS:colorCorrection"),
        P("cc_num_params", "OMFI:FXPS:ccNumParams"),
    ]

    def keyframes(self) -> List[Dict[str, Any]]:
        """The per-keyframe fields, zipped into one dict per keyframe.

        Only fields the file actually wrote appear; a keyframe that set nothing
        is dropped rather than returned as an empty dict.
        """
        names = [p.name for p in self._propertydefs_by_name.values() if p.multi]
        columns = {n: self.values(self._propertydefs_by_name[n].omf_name) for n in names}
        count = max((len(v) for v in columns.values()), default=0)
        out = []
        for i in range(count):
            frame = {n: v[i] for n, v in columns.items() if i < len(v)}
            if frame:
                out.append(frame)
        return out

    def _repr_extra(self):
        return "%s keyframes" % (self.num_keyframes
                                 if self.num_keyframes is not None
                                 else len(self.keyframes()))


@register_class
class ColorCorrection(OMFObject):
    """``ATRE`` -- an effect reference carrying a colour-correction payload.

    The schema declares exactly one property for it, misspelled ``EfffectID``
    with three fs.  Bound as written.
    """

    class_id = "ATRE"
    __slots__ = ()
    propertydefs = [
        P("effect_id", "OMFI:ATRE:EfffectID",
          doc="spelled 'EfffectID' in the schema -- Avid's typo, preserved"),
    ]


@register_class
class GraphicEffect(OMFObject):
    """``GRFX`` -- an imported still or matte, held as a picture blob."""

    class_id = "GRFX"
    __slots__ = ()
    propertydefs = [
        P("pict_data", "OMFI:MC:GRFX:PictData"),
        P("pict_size", "OMFI:MC:GRFX:PictSize"),
        P("vc_id", "OMFI:MC:GRFX:vcID"),
    ]

    def _repr_extra(self):
        return "%s bytes" % self.pict_size if self.pict_size else ""
