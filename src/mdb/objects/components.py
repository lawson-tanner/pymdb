"""``CPNT`` and its descendants -- the things that occupy time on a track.

The hierarchy is OMF's own::

    Component (CPNT)
      Clip (CLIP)
        SourceClip (SCLP)      the derivation link
        Filler (FILL)
        Timecode (TCCP)
        Edgecode (ECCP)        film edge numbers
        TrackRef (TRKR)
        ParamClip (PRCL)       an animated parameter
        ControlClip (CTRL)     the older control-point form
      Sequence (SEQU)
      TrackGroup (TRKG)        -- see :mod:`mdb.objects.trackgroups`

``PRCL`` and ``CTRL`` carry their control points as flat, parallel properties
(``NumPts`` plus per-point values) rather than as sub-objects, so the point
list is assembled by :meth:`ParamClip.control_points` rather than being a
property in its own right.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional

from .. import enums
from ..core import MDBObject, PropertyDef as P, register_class
from ..mobid import MobID, ShortUID
from .attributes import AttributeList
from .base import OMFObject

if TYPE_CHECKING:  # pragma: no cover
    from .trackgroups import Mob

__all__ = ["Component", "Clip", "SourceClip", "Filler", "Timecode", "Edgecode",
           "TrackRef", "Sequence", "ParamClip", "ControlClip"]


@register_class
class Component(OMFObject):
    """``CPNT`` -- anything with an edit rate and a track kind."""

    class_id = "CPNT"
    __slots__ = ()
    propertydefs = [
        P("edit_rate", "OMFI:CPNT:EditRate"),
        P("name", "OMFI:CPNT:Name"),
        P("track_kind", "OMFI:CPNT:TrackKind", enum=enums.TRACK_TYPE),
        P("attributes", "OMFI:CPNT:Attributes", deref=True),
        P("session_attrs", "OMFI:CPNT:SessionAttrs", deref=True,
          doc="attributes scoped to the editing session rather than the media"),
        P("effect_id", "OMFI:CPNT:EffectID",
          doc="the Avid effect this component realises, e.g. 'EFF_BLEND_DISSOLVE'"),
        P("param_list", "OMFI:CPNT:ParamList", deref=True, doc="PRLS of PRIT parameters"),
        P("precomputed", "OMFI:CPNT:Precomputed", deref=True,
          doc="the rendered mob standing in for this component"),
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


@register_class
class Clip(Component):
    """``CLIP`` -- a component with a duration."""

    class_id = "CLIP"
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


@register_class
class Edgecode(Clip):
    """``ECCP`` -- film edge numbers, the film-side twin of ``TCCP``.

    Absent from both reference samples (an MDB indexes digital media, and film
    mobs arrive only on projects that captured from film).  The property set
    is taken from the schema of both samples; the semantics are OMF 2.1's.
    """

    class_id = "ECCP"
    __slots__ = ()
    propertydefs = [
        P("start_ec", "OMFI:ECCP:StartEC", doc="edge code at the start of the clip"),
        P("film_kind", "OMFI:ECCP:FilmKind", enum=enums.FILM_TYPE),
        P("code_format", "OMFI:ECCP:CodeFormat", enum=enums.EDGE_TYPE),
        P("base_perf", "OMFI:ECCP:BasePerf", doc="perforations per edge-code increment"),
        P("header", "OMFI:ECCP:Header", doc="the manufacturer prefix printed on the stock"),
    ]

    def _repr_extra(self):
        return "%s %s" % (self.film_kind_name, self.start_ec)


class _PointList(Clip):
    """Shared plumbing for the two control-point clips.

    ``PRCL`` and ``CTRL`` both store a point count and then the points
    themselves as repeated properties rather than as objects, so the *n*-th
    point is the *n*-th value of each per-point property.  Reading them means
    zipping those parallel lists, which is what :meth:`control_points` does.
    """

    __slots__ = ()

    #: ``(python name, OMF property)`` pairs read once per point, in order.
    point_properties: tuple = ()

    def control_points(self) -> List[Dict[str, Any]]:
        """The control points, as dicts, in file order.

        Returns one dict per point with whichever of :attr:`point_properties`
        the file actually wrote.  Points are *not* padded out to
        ``NumPts``: a short property list means the file is short, and
        inventing ``None``s would hide that.
        """
        columns = {name: self.values(omf) for name, omf in self.point_properties}
        count = max((len(v) for v in columns.values()), default=0)
        out: List[Dict[str, Any]] = []
        for i in range(count):
            point = {name: values[i] for name, values in columns.items()
                     if i < len(values)}
            if point:
                out.append(point)
        return out

    def _repr_extra(self):
        return "%s, %d points" % (self.interp_kind_name, len(self.control_points()))


@register_class
class ParamClip(_PointList):
    """``PRCL`` -- an animated effect parameter: a curve of control points.

    The value at each point can be an integer, a double or a user blob;
    ``ValueType`` says which, and :meth:`control_points` returns whichever the
    file wrote.  Absent from both reference samples -- effects live in the
    ``.avb`` bin, and only their rendered media reaches the MDB.
    """

    class_id = "PRCL"
    __slots__ = ()
    point_properties = (
        ("offset_num", "OMFI:PRCL:OffsetNum"),
        ("offset_den", "OMFI:PRCL:OffsetDen"),
        ("time_scale", "OMFI:PRCL:TimeScale"),
        ("value_integer", "OMFI:PRCL:ValueInteger"),
        ("value_double", "OMFI:PRCL:ValueDouble"),
        ("value_user", "OMFI:PRCL:ValueUser"),
        ("pp_code", "OMFI:PRCL:PPCode"),
        ("pp_type", "OMFI:PRCL:PPType"),
        ("pp_integer", "OMFI:PRCL:PPInteger"),
        ("pp_double", "OMFI:PRCL:PPDouble"),
    )
    structural_properties = tuple(omf for _, omf in point_properties)
    propertydefs = [
        P("interp_kind", "OMFI:PRCL:InterpKind", enum=enums.INTERP_KIND),
        P("extrap_kind", "OMFI:PCRL:ExtrapKind", enum=enums.EXTRAP_KIND,
          doc="spelled 'PCRL' in the schema -- Avid's typo, preserved"),
        P("value_type", "OMFI:PRCL:ValueType", enum=enums.PARAM_VALUE_TYPE),
        P("value_range", "OMFI:PRCL:ValueRange"),
        P("num_points", "OMFI:PRCL:NumPts"),
        P("num_point_properties", "OMFI:PRCL:NumPPs"),
        P("has_value", "OMFI:PRCL:HasValue"),
        P("fields", "OMFI:PRCL:Fields"),
        P("control_point_refs", "OMFI:PRCL:ControlPoints", deref=True),
        P("point_property_refs", "OMFI:PRCL:PPs", deref=True),
    ]


@register_class
class ControlClip(_PointList):
    """``CTRL`` -- the older, rational-valued control curve ``PRCL`` replaced.

    Same shape as :class:`ParamClip` but with numerator/denominator values and
    an interpolation-quality (``IQ``) block.  Absent from both reference
    samples.
    """

    class_id = "CTRL"
    __slots__ = ()
    point_properties = (
        ("offset_num", "OMFI:CTRL:OffsetNum"),
        ("offset_den", "OMFI:CTRL:OffsetDen"),
        ("time_scale", "OMFI:CTRL:TimeScale"),
        ("value_num", "OMFI:CTRL:ValueNum"),
        ("value_den", "OMFI:CTRL:ValueDen"),
        ("pp_code", "OMFI:CTRL:PPCode"),
        ("pp_num", "OMFI:CTRL:PPNum"),
        ("pp_den", "OMFI:CTRL:PPDen"),
    )
    structural_properties = (
        tuple(omf for _, omf in point_properties)
        + tuple("OMFI:INTL:IQ%s%d" % (part, i)
                for part in ("Kind", "Num", "Den") for i in range(10)))
    propertydefs = [
        P("interp_kind", "OMFI:CTRL:InterpKind", enum=enums.INTERP_KIND),
        P("value", "OMFI:CTRL:Value"),
        P("value_range", "OMFI:CTRL:ValueRange"),
        P("num_points", "OMFI:CTRL:NumPts"),
        P("num_point_properties", "OMFI:CTRL:NumPPs"),
        P("num_iqs", "OMFI:CTRL:NumIQs"),
        P("has_value", "OMFI:CTRL:HasValue"),
        P("control_point_refs", "OMFI:CTRL:ControlPoints", deref=True),
        P("point_property_refs", "OMFI:CTRL:PPs", deref=True),
        P("iq_refs", "OMFI:CTRL:IQs", deref=True),
    ]

    def interpolation_qualities(self) -> List[Dict[str, Any]]:
        """The ``INTL`` interpolation-quality block, if the file carries one.

        The schema spells this as ten numbered triples
        (``IQKind0..9`` / ``IQNum0..9`` / ``IQDen0..9``) written flat on the
        clip rather than as a list, so it is read by index.
        """
        out: List[Dict[str, Any]] = []
        for i in range(10):
            entry = {}
            for key, prefix in (("kind", "IQKind"), ("num", "IQNum"), ("den", "IQDen")):
                value = self.get("OMFI:INTL:%s%d" % (prefix, i))
                if value is not None:
                    entry[key] = value
            if entry:
                out.append(entry)
        return out
