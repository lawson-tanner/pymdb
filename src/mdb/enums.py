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
           "LAYOUT_TYPE", "COLOR_SITING", "label"]

#: ``omfi:AttrKind`` -- which ATTB value property is populated.  [V]
#: 1/2/3 verified by co-occurrence with Int/String/Obj attributes; 4 verified
#: as the "bob" blob form (``ATTB:BobData`` + ``ATTB:BobSize``, no *Attribute).
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
