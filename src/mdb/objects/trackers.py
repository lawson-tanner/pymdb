"""The tracker family: ``TKMN``, ``TKDS``, ``TKPS``, ``TKDA``, ``TKPA``.

Media Composer's stabiliser and corner-pin trackers store their analysis
separately from the effect that consumes it, so the same tracking data can
drive several parameters.  The shape is::

    TKMN (manager)
      -> TKDS (data slots)   -> TKDA (tracking data)   -> tracker clips
      -> TKPS (param slots)  -> TKPA (tracked param)

The class dictionary of both reference samples declares all five as roots with
no parent, and none of them appears in either sample.  Settings blobs are left
as bytes: they are Media Composer's private serialisation, and guessing at
their layout would be inventing rather than reading.
"""
from __future__ import annotations

from typing import List

from ..core import PropertyDef as P, register_class
from .base import OMFObject

__all__ = ["TrackerManager", "TrackerDataSlot", "TrackerParameterSlot",
           "TrackerData", "TrackerParameter"]


@register_class
class TrackerManager(OMFObject):
    """``TKMN`` -- the root of one effect's tracking setup."""

    class_id = "TKMN"
    __slots__ = ()
    propertydefs = [
        P("data_slots", "OMFI:TKMN:TrackerDataSlots", deref=True),
        P("param_slots", "OMFI:TKMN:TrackedParamSlots", deref=True),
    ]


@register_class
class TrackerDataSlot(OMFObject):
    """``TKDS`` -- a slot holding one or more :class:`TrackerData` analyses."""

    class_id = "TKDS"
    __slots__ = ()
    propertydefs = [
        P("num_data_slots", "OMFI:TKDS:NumDataSlots"),
        P("tracker_data", "OMFI:TKDS:TrackerData", deref=True),
        P("tracker_data_ids", "OMFI:TKDS:TrackerDataIDs"),
        P("track_foreground", "OMFI:TKDAS:TrackForeground",
          doc="declared under the 'TKDAS' prefix, which appears nowhere else"),
    ]


@register_class
class TrackerParameterSlot(OMFObject):
    """``TKPS`` -- a slot binding tracking data to the parameters it drives."""

    class_id = "TKPS"
    __slots__ = ()
    propertydefs = [
        P("num_param_slots", "OMFI:TKPS:NumParamSlots"),
        P("tracked_param", "OMFI:TKPS:TrackedParam", deref=True),
        P("tracker_param_ids", "OMFI:TKPS:TrackerParamIDs"),
        P("effect_settings", "OMFI:TKPS:EffectSettings"),
        P("effect_settings_size", "OMFI:TKPS:EffectSettingsSize"),
    ]


@register_class
class TrackerData(OMFObject):
    """``TKDA`` -- one tracker's analysis: its settings and its clips."""

    class_id = "TKDA"
    __slots__ = ()
    propertydefs = [
        P("num_tracker_clips", "OMFI:TKDA:NumTrackerClips"),
        P("tracker_clips", "OMFI:TKDA:TrackerClip", deref=True, multi=True),
        P("tracker_clip_ids", "OMFI:TKDA:TrackerClipIDs"),
        P("tracker_clip_version", "OMFI:TKDA:TrackerClipVersion"),
        P("settings", "OMFI:TKDA:TrackerSettings"),
        P("settings_size", "OMFI:TKDA:TrackerSettingsSize"),
        P("smoothing", "OMFI:TKDA:TrackerSmoothing"),
        P("jitter_removal", "OMFI:TKDA:TrackerJitterRemoval"),
        P("filter_data_amount", "OMFI:TKDA:TrackerFilterDataAmt"),
        P("offset_tracking", "OMFI:TKDA:TrackerOffsetTracking"),
    ]

    def clips(self) -> List[object]:
        """Every tracker clip, flattened -- ``TrackerClip`` repeats per clip."""
        out = []
        for value in (self.tracker_clips or []):
            out.extend(value if isinstance(value, list) else [value])
        return out


@register_class
class TrackerParameter(OMFObject):
    """``TKPA`` -- one parameter driven by tracking data."""

    class_id = "TKPA"
    __slots__ = ()
    propertydefs = [
        P("settings", "OMFI:TKPA:ParamSettings"),
        P("settings_size", "OMFI:TKPA:ParamSettingsSize"),
    ]
