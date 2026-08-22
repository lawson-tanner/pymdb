"""Enumerated values.

Confidence markers follow the briefing document's convention:
``[V]`` verified against both reference samples, ``[I]`` inferred with high
confidence from OMF 2.1, ``[?]`` unknown.  Lookups never raise -- an
unrecognised value comes back as ``"<name>(7)"`` so new codes stay visible
instead of being swallowed.
"""
from __future__ import annotations

from typing import Dict, Optional

__all__ = ["ATTR_KIND", "TRACK_TYPE", "PHYSICAL_MOB_TYPE", "USAGE_CODE",
           "LAYOUT_TYPE", "COLOR_SITING", "EDGE_TYPE", "FILM_TYPE",
           "INTERP_KIND", "EXTRAP_KIND", "PARAM_VALUE_TYPE",
           "REFORMATTING_OPTION", "label"]

#: ``omfi:AttrKind`` -- which ATTB value property is populated.  [V]
#: 1/2/3 verified by co-occurrence with Int/String/Obj attributes; 4 verified
#: as the "bob" blob form (``ATTB:BobData`` + ``ATTB:BobSize``, no ``*Attribute``).
ATTR_KIND: Dict[int, str] = {
    0: "null",
    1: "int",
    2: "string",
    3: "object",
    4: "bob",
}

#: ``omfi:TrackType`` (OMF ``omfTrackType_t``).  [V] for 0-3
TRACK_TYPE: Dict[int, str] = {
    0: "none",        # mobs and track groups carry 0
    1: "picture",
    2: "sound",
    3: "timecode",
    4: "edgecode",
    5: "attribute",
    6: "effect",
}

#: ``omfi:PhysicalMobType`` on ``MDES:MobKind``.  [I] from OMF 2.1;
#: only 1 and 5 observed in the reference samples.
PHYSICAL_MOB_TYPE: Dict[int, str] = {
    0: "null",
    1: "file",
    2: "tape",
    3: "film",
    4: "nagra",
    5: "unknown",
}

#: ``omfi:UsageCodeType`` on ``MOBJ:UsageCode``.  [?] -- 0, 1 and 7 observed;
#: 0 dominates source-side mobs and 7 appears on the transcoded sample's
#: master-side mobs, but Avid publishes no table.
USAGE_CODE: Dict[int, str] = {
    0: "none",
    1: "composition",
    7: "master",
}

#: ``omfi:LayoutType`` (OMF ``omfFrameLayout_t``).  [I]
LAYOUT_TYPE: Dict[int, str] = {
    0: "full_frame",
    1: "separate_fields",
    2: "single_field",
    3: "mixed_fields",
    4: "segmented_frame",
}

#: ``omfi:ColorSitingType``.  [I]
COLOR_SITING: Dict[int, str] = {
    0: "cosited",
    1: "averaged",
    2: "three_tap",
    255: "unknown",
}


def label(table: Dict[int, str], value: Optional[int], name: str = "value") -> str:
    """Name a numeric code, keeping unknown codes visible rather than hiding them."""
    if value is None:
        return "<unset>"
    try:
        return table[value]
    except (KeyError, TypeError):
        return "%s(%r)" % (name, value)


#: ``omfi:EdgeType`` (OMF ``omfEdgeType_t``) on ``ECCP:CodeFormat``.  [I] from
#: OMF 2.1 -- no ``ECCP`` object exists in either reference sample.
EDGE_TYPE: Dict[int, str] = {
    0: "null",
    1: "keycode",
    2: "ink",
    3: "aux",
}

#: ``omfi:FilmType`` (OMF ``omfFilmType_t``) on ``ECCP:FilmKind``.  [I]
FILM_TYPE: Dict[int, str] = {
    0: "null",
    1: "35mm",
    2: "16mm",
    3: "8mm",
    4: "65mm",
}

#: Interpolation between control points, on ``PRCL:InterpKind`` and
#: ``CTRL:InterpKind``.  [I] -- names follow pyavb's reading of the AVB
#: container, where the same codes drive the same curves; no ``PRCL`` or
#: ``CTRL`` object exists in either reference sample to check them against.
INTERP_KIND: Dict[int, str] = {
    0: "constant",
    1: "linear",
    2: "bezier",
    3: "cubic",
    4: "spline",
}

#: How a curve behaves outside its first and last control point, on
#: ``PCRL:ExtrapKind`` (Avid's spelling).  [?] -- inferred by symmetry with
#: :data:`INTERP_KIND`; unverified.
EXTRAP_KIND: Dict[int, str] = {
    0: "constant",
    1: "linear",
}

#: Which value property of a parameter is populated, on ``PRIT:ValueType`` and
#: ``PRCL:ValueType``.  [I] from the property sets: a ``PRCL`` carries
#: ``ValueInteger``, ``ValueDouble`` and ``ValueUser`` and writes one of them.
PARAM_VALUE_TYPE: Dict[int, str] = {
    1: "integer",
    2: "double",
    3: "user",
    4: "reference",
}

#: ``DIDD:ReformattingOption`` -- how a raster that does not match the project
#: is fitted to it.  [?] -- absent from both samples; names are Media
#: Composer's UI labels for the same choice.
REFORMATTING_OPTION: Dict[int, str] = {
    0: "none",
    1: "stretch",
    2: "center_crop",
    3: "pad",
}
