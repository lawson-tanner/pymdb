"""The OMF / Avid class vocabulary.

The property tables in the modules below were derived by census over the two
reference samples -- every property name the files' own schema registry
declares, with the type each declares for it -- then named against the OMF
Interchange 2.1 specification and pyavb's equivalent vocabulary for the AVB
container.  Where the two disagree, the file wins and the divergence is noted
in the class's docstring.

Many of these classes never appear in the reference samples, and that is the
expected result rather than a gap: an MDB indexes media files, so it carries
mobs, descriptors and locators in quantity, and carries effects, markers and
embedded essence only if something unusual has happened.  They are defined
anyway because the samples' *schema* declares them -- 759 property names
across roughly a hundred class prefixes -- so a file that does use one reads
as a typed object rather than as a bag of names.

The modules mirror pyavb's layout:

===========================  ==================================================
:mod:`~mdb.objects.base`     ``OMFObject``, ``HEAD``
:mod:`~mdb.objects.attributes` ``ATTR`` / ``ATTB`` -- the Avid attribute tree
:mod:`~mdb.objects.locators` ``WINL``, ``MSML`` and the rest of the path classes
:mod:`~mdb.objects.descriptors` ``MDES`` and every essence descriptor
:mod:`~mdb.objects.misc`     links, markers, list containers, ``CLSD``
:mod:`~mdb.objects.components` ``CPNT`` and its clips
:mod:`~mdb.objects.trackgroups` ``TRKG``, ``MOBJ``, ``TRAK``, ``SLCT``
:mod:`~mdb.objects.effects`  ``TKFX``, ``TNFX``, the time warps
:mod:`~mdb.objects.parameters` ``PRIT``, ``PRLS``, ``FXPS`` and friends
:mod:`~mdb.objects.trackers` the ``TKMN`` tracker family
:mod:`~mdb.objects.media`    embedded essence, which an MDB never carries
===========================  ==================================================

Everything is re-exported here, so ``from mdb.objects import Mob`` keeps
working and ``import mdb; mdb.Mob`` does too.

Import order matters only in that each module imports the ones above it in the
table; there are no cycles.
"""
from __future__ import annotations

from .base import OMFObject, Header
from .attributes import AttributeList, Attribute
from .locators import (Locator, WindowsLocator, DOSLocator, MacLocator,
                       UnixLocator, TextLocator, MediaStreamLink,
                       DirectoryLocator, MacDirectoryLocator,
                       UnixDirectoryLocator, DomainLocator, AssetManagerLocator)
from .descriptors import (MediaDescriptor, TapeDescriptor, FilmDescriptor,
                          NagraDescriptor, FileDescriptor, MultiDescriptor,
                          DigitalImageDescriptor, CDCIDescriptor, RGBADescriptor,
                          JPEGDescriptor, MPEGDescriptor, TIFFDescriptor,
                          DVDescriptor, VideoDescriptor, VC1Descriptor,
                          AudioDescriptor, PCMADescriptor, MPEGAudioDescriptor,
                          WAVEDescriptor, AIFCDescriptor, SoundDesignerDescriptor,
                          DataDescriptor, ANCDataDescriptor, VBIDataDescriptor,
                          Rect)
from .misc import (BinLink, MobReference, Marker, TimeCrumbList, SortedList,
                   ListItem, ClassDescriptor, MediaFileLink, MediaFileBlock,
                   ControlCode, AttributeClip, MediaStreamProject, Domain,
                   SoundDesignerLink, UserProperty)
from .components import (Component, Clip, SourceClip, Filler, Timecode,
                         Edgecode, TrackRef, Sequence, ParamClip, ControlClip)
from .trackgroups import TrackGroup, Mob, RepeatSet, Track, Selector
from .effects import (TrackEffect, PanVolumeEffect, AudioSuitePluginEffect,
                      EqualizerMultiBand, EqualizerBand, InlineEqualizerBand,
                      TimeWarp, CaptureMask,
                      StrobeEffect, MotionEffect, Repeat, Transition,
                      TransitionEffect)
from .parameters import (ParameterItem, ParameterList, UserParameter,
                         EffectParamList, GraphicEffect, ColorCorrection)
from .trackers import (TrackerManager, TrackerDataSlot, TrackerParameterSlot,
                       TrackerData, TrackerParameter)
from .media import (MediaData, WAVEData, AIFCData, TIFFData, AvidMediaData,
                    ImageData, JPEGFrameIndex, MPEGFrameIndex)

__all__ = [
    # base
    "OMFObject", "Header",
    # attributes
    "AttributeList", "Attribute",
    # locators
    "Locator", "WindowsLocator", "DOSLocator", "MacLocator", "UnixLocator",
    "TextLocator", "MediaStreamLink", "DirectoryLocator", "MacDirectoryLocator",
    "UnixDirectoryLocator", "DomainLocator", "AssetManagerLocator",
    # descriptors
    "MediaDescriptor", "TapeDescriptor", "FilmDescriptor", "NagraDescriptor",
    "FileDescriptor", "MultiDescriptor", "DigitalImageDescriptor",
    "CDCIDescriptor", "RGBADescriptor", "JPEGDescriptor", "MPEGDescriptor",
    "TIFFDescriptor", "DVDescriptor", "VideoDescriptor", "VC1Descriptor",
    "AudioDescriptor", "PCMADescriptor", "MPEGAudioDescriptor", "WAVEDescriptor",
    "AIFCDescriptor", "SoundDesignerDescriptor", "DataDescriptor",
    "ANCDataDescriptor", "VBIDataDescriptor", "Rect",
    # misc
    "BinLink", "MobReference", "Marker", "TimeCrumbList", "SortedList",
    "ListItem", "ClassDescriptor", "MediaFileLink", "MediaFileBlock",
    "ControlCode", "AttributeClip", "MediaStreamProject", "Domain",
    "SoundDesignerLink", "UserProperty",
    # components
    "Component", "Clip", "SourceClip", "Filler", "Timecode", "Edgecode",
    "TrackRef", "Sequence", "ParamClip", "ControlClip",
    # track groups
    "TrackGroup", "Mob", "RepeatSet", "Track", "Selector",
    # effects
    "TrackEffect", "PanVolumeEffect", "AudioSuitePluginEffect",
    "EqualizerMultiBand", "EqualizerBand", "InlineEqualizerBand",
    "TimeWarp", "CaptureMask",
    "StrobeEffect", "MotionEffect", "Repeat", "Transition", "TransitionEffect",
    # parameters
    "ParameterItem", "ParameterList", "UserParameter", "EffectParamList",
    "GraphicEffect", "ColorCorrection",
    # trackers
    "TrackerManager", "TrackerDataSlot", "TrackerParameterSlot", "TrackerData",
    "TrackerParameter",
    # media data
    "MediaData", "WAVEData", "AIFCData", "TIFFData", "AvidMediaData",
    "ImageData", "JPEGFrameIndex", "MPEGFrameIndex",
]
