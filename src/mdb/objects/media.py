"""Media-data classes: essence carried *inside* the container.

An OMF file may embed its essence; an MDB never does -- it is an index of
files on disk, which is why ``HEAD:MediaData`` is empty in both reference
samples and every class here is unused in them.  They are bound because the
schema declares them, and because the same class names appear in OMF files
that a caller may hand to this reader by mistake: getting a typed
``WAVEData`` back with an empty ``data`` property is a better answer than a
generic object.

Each of these joins to its mob by MobID value rather than by object reference,
the same way ``MSML`` does.

Note the naming split against pyavb: in OMF the descriptor and the media data
are separate classes (``WAVD`` describes, ``WAVE`` holds), and both are
declared in the MDB schema.  pyavb folds them together under the data-class
name because the AVB container does.  The descriptors live in
:mod:`mdb.objects.descriptors`.
"""
from __future__ import annotations

from typing import Optional

from ..core import PropertyDef as P, register_class
from .base import OMFObject

__all__ = ["MediaData", "WAVEData", "AIFCData", "TIFFData", "AvidMediaData",
           "ImageData", "JPEGFrameIndex", "MPEGFrameIndex"]


@register_class
class MediaData(OMFObject):
    """``MDAT`` -- the base for embedded essence: a MobID and a payload."""

    class_id = "MDAT"
    __slots__ = ()
    propertydefs = [P("mob_id", "OMFI:MDAT:MobID")]

    #: The OMF property this subclass keeps its payload in.
    data_property: Optional[str] = None

    @property
    def data(self):
        """The payload bytes, or ``None`` when the class carries none."""
        return self.get(self.data_property) if self.data_property else None

    @property
    def size(self) -> Optional[int]:
        data = self.data
        return None if data is None else len(data)

    def _repr_extra(self):
        size = self.size
        return "" if size is None else "%d bytes" % size


@register_class
class WAVEData(MediaData):
    """``WAVE`` -- embedded Broadcast WAVE essence.

    Described by :class:`~mdb.objects.descriptors.WAVEDescriptor` (``WAVD``).
    """

    class_id = "WAVE"
    data_property = "OMFI:WAVE:Data"
    __slots__ = ()
    propertydefs = [
        P("mob_id", "OMFI:WAVE:MobID"),
        P("wave_data", "OMFI:WAVE:Data"),
        P("version", "OMFI:WAVE:Version"),
    ]


@register_class
class AIFCData(MediaData):
    """``AIFC`` -- embedded AIFF-C essence.

    Described by :class:`~mdb.objects.descriptors.AIFCDescriptor` (``AIFD``).
    """

    class_id = "AIFC"
    data_property = "OMFI:AIFC:Data"
    __slots__ = ()
    propertydefs = [
        P("mob_id", "OMFI:AIFC:MobID"),
        P("aifc_data", "OMFI:AIFC:Data"),
        P("version", "OMFI:AIFC:Version"),
    ]


@register_class
class TIFFData(MediaData):
    """``TIFF`` -- embedded TIFF essence.

    Described by :class:`~mdb.objects.descriptors.TIFFDescriptor` (``TIFD``).
    """

    class_id = "TIFF"
    data_property = "OMFI:TIFF:Data"
    __slots__ = ()
    propertydefs = [
        P("mob_id", "OMFI:TIFF:MobID"),
        P("tiff_data", "OMFI:TIFF:Data"),
        P("version", "OMFI:TIFF:Version"),
    ]


@register_class
class AvidMediaData(MediaData):
    """``MVC1`` -- embedded essence in an Avid-private codec."""

    class_id = "MVC1"
    data_property = "OMFI:MVC1:Data"
    __slots__ = ()
    propertydefs = [
        P("mob_id", "OMFI:MVC1:MobID"),
        P("mvc1_data", "OMFI:MVC1:Data"),
    ]


@register_class
class ImageData(MediaData):
    """``IDAT`` -- embedded image essence, the generic form."""

    class_id = "IDAT"
    data_property = "OMFI:IDAT:ImageData"
    __slots__ = ()
    propertydefs = [P("image_data", "OMFI:IDAT:ImageData")]


@register_class
class JPEGFrameIndex(OMFObject):
    """``JPEG`` -- the frame index for motion-JPEG essence.

    Separate from :class:`~mdb.objects.descriptors.JPEGDescriptor` (``JPED``):
    the descriptor says how to decode a frame, this says where each one starts.
    """

    class_id = "JPEG"
    __slots__ = ()
    propertydefs = [P("frame_index", "OMFI:JPEG:FrameIndex")]


@register_class
class MPEGFrameIndex(OMFObject):
    """``MPEG`` -- the frame index for MPEG essence."""

    class_id = "MPEG"
    __slots__ = ()
    propertydefs = [P("frame_index", "OMFI:MPEG:FrameIndex")]
