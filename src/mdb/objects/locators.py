"""Locators -- how an object says where something lives.

Two families share one base.  *File* locators (``WINL``, ``DOSL``, ``MACL``,
``UNXL``) name a file; *directory* locators (``DL``, ``MACDL``, ``UNXDL``)
name the folder around it.  ``TXTL`` is a free-text locator, and ``MSML`` --
Avid's media-stream link -- is a ``TXTL`` subclass, which is why a
descriptor's ``MDES:Locator`` array mixes paths and volume names in one list.

Each concrete class also declares its own ``PathName`` alongside the shared
``FL:PathName``.  Media Composer writes the shared one; the per-class
spellings are in the schema of both reference samples and are bound here so a
file that uses them still reads.
"""
from __future__ import annotations

from typing import List, Optional

from ..core import PropertyDef as P, register_class
from .base import OMFObject

__all__ = ["Locator", "WindowsLocator", "DOSLocator", "MacLocator",
           "UnixLocator", "TextLocator", "MediaStreamLink", "DirectoryLocator",
           "MacDirectoryLocator", "UnixDirectoryLocator", "DomainLocator",
           "AssetManagerLocator"]


class Locator(OMFObject):
    """Base for the locator classes: a path, in one or more spellings.

    Avid writes both a legacy code-page ``FL:PathName`` and a
    ``FL:PathNameUTF8`` twin, and a locator can carry more than one of either
    (an empty one plus the real path is common), so all values are exposed.

    Subclasses may add their own path spelling -- ``UNXL:PathName``,
    ``DOSL:PathName``, ``DL:PathNameUTF8``.  :attr:`path` and :meth:`all_paths`
    consider every path-shaped property the class declares, UTF-8 first, so a
    subclass gets the right answer without overriding anything.
    """

    #: OMF property names, most preferred first, that this class may spell a
    #: path in.  Subclasses prepend their own; the shared ``FL`` pair is the
    #: fallback every locator understands.
    path_properties = ("OMFI:FL:PathNameUTF8", "OMFI:FL:PathName",
                       "OMFI:FL:POSIXPathName")

    __slots__ = ()
    propertydefs = [
        P("path_name", "OMFI:FL:PathName"),
        P("path_name_utf8", "OMFI:FL:PathNameUTF8"),
        P("path_name_posix", "OMFI:FL:POSIXPathName"),
    ]

    @property
    def path(self) -> Optional[str]:
        """The best available path: the last non-empty UTF-8 value, else legacy."""
        for name in self.path_properties:
            for candidate in reversed(self.values(name)):
                if candidate:
                    return candidate
        return None

    def all_paths(self) -> List[str]:
        """Every distinct non-empty path spelling this locator carries."""
        seen, out = set(), []
        for name in self.path_properties:
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
    path_properties = ('OMFI:DOSL:PathName',) + Locator.path_properties
    propertydefs = [
        P('dos_path_name', 'OMFI:DOSL:PathName'),
    ]


@register_class
class MacLocator(Locator):
    """``MACL`` -- a Macintosh path."""
    class_id = "MACL"
    __slots__ = ()
    path_properties = ('OMFI:MACL:FileName',) + Locator.path_properties
    propertydefs = [
        P('mac_file_name', 'OMFI:MACL:FileName'),
        P('vref', 'OMFI:MACL:VRef'),
        P('dir_id', 'OMFI:MACL:DirID'),
        P('sds_address', 'OMFI:MACL:SDSAddress'),
        P('sds_mob_id', 'OMFI:MACL:SDSMobID'),
    ]


@register_class
class UnixLocator(Locator):
    """``UNXL`` -- a Unix path."""
    class_id = "UNXL"
    __slots__ = ()
    path_properties = ('OMFI:UNXL:PathName',) + Locator.path_properties
    propertydefs = [
        P('unix_path_name', 'OMFI:UNXL:PathName'),
    ]


@register_class
class TextLocator(Locator):
    """``TXTL`` -- a free-text locator; parent class of MSML."""
    class_id = "TXTL"
    __slots__ = ()
    path_properties = ('OMFI:TXTL:Name',) + Locator.path_properties
    propertydefs = [
        P('text_name', 'OMFI:TXTL:Name'),
    ]


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


# --------------------------------------------------------------------------
# directory locators -- the folder around the file
# --------------------------------------------------------------------------
@register_class
class DirectoryLocator(Locator):
    """``DL`` -- a directory rather than a file.

    Declared in the schema of both samples and written in neither.  It shares
    the ``FL``-style path pair, so :attr:`~Locator.path` behaves the same.
    """

    class_id = "DL"
    __slots__ = ()
    path_properties = ('OMFI:DL:PathNameUTF8', 'OMFI:DL:PathName') + Locator.path_properties
    propertydefs = [
        P("dir_path_name", "OMFI:DL:PathName"),
        P("dir_path_name_utf8", "OMFI:DL:PathNameUTF8"),
    ]

@register_class
class MacDirectoryLocator(DirectoryLocator):
    """``MACDL`` -- a classic Mac OS directory, addressed by volume reference
    and directory ID rather than by path."""

    class_id = "MACDL"
    __slots__ = ()
    path_properties = ('OMFI:MACDL:FileName',) + DirectoryLocator.path_properties
    propertydefs = [
        P("vref", "OMFI:MACDL:VRef", doc="volume reference number"),
        P("dir_id", "OMFI:MACDL:DirID"),
        P("file_name", "OMFI:MACDL:FileName"),
    ]


@register_class
class UnixDirectoryLocator(DirectoryLocator):
    """``UNXDL`` -- a Unix directory."""

    class_id = "UNXDL"
    __slots__ = ()
    path_properties = ('OMFI:UNXDL:PathName',) + DirectoryLocator.path_properties
    propertydefs = [P("unix_dir_path", "OMFI:UNXDL:PathName")]


@register_class
class DomainLocator(TextLocator):
    """``DOML`` -- a locator naming a domain rather than a filesystem.

    The class dictionary of both samples declares ``DOML -> TXTL``; the only
    property the schema carries for it is the near-universal ``AMEVersion``,
    so what a domain name looks like here is unverified.
    """

    class_id = "DOML"
    __slots__ = ()


@register_class
class AssetManagerLocator(OMFObject):
    """``OMML`` -- an asset-management reference: which system owns this media.

    Written by Interplay and similar asset managers.  Absent from both
    reference samples; the two properties below are the whole of what the
    schema declares.
    """

    class_id = "OMML"
    __slots__ = ()
    propertydefs = [
        P("asset_id", "OMFI:OMML:AssetID"),
        P("asset_manager", "OMFI:OMML:AssetManager"),
    ]

    def _repr_extra(self):
        return repr(self.asset_manager) if self.asset_manager else ""
