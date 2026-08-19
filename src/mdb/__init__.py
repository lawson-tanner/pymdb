"""pymdb -- read Avid Media Composer ``msmMMOB.mdb`` media databases.

An MDB is the index Media Composer keeps inside each Avid media folder: one
entry per media file, with clip names, MobIDs, paths, track structure and
essence descriptors.  Physically it is an OMF Interchange 1.x object database
in a Bento container -- and it has no header, so the only correct way in is
the last 24 bytes of the file.

Quick start::

    import mdb

    with mdb.open("Avid MediaFiles/MXF/1/msmMMOB.mdb") as f:
        print(f.summary()["classes"])
        for mob in f.mobs:
            print(mob.name, mob.descriptor.summary() if mob.descriptor else "",
                  mob.paths())

Two layers are available.  :class:`~mdb.file.MDBFile` gives you named,
typed objects; :class:`~mdb.bento.BentoContainer` underneath gives you the
raw TOC when you need to answer questions the object model does not cover
("which entry owns byte 0x1f40?").

This package reads; it does not write.  Media Composer updates these files in
place, so treat them as read-only evidence.
"""
from __future__ import annotations

from .bento import (BentoContainer, ContainerLabel, CorruptContainer,
                    BentoError, NotABentoContainer, TOCEntry)
from .core import MDBObject, PropertyDef, UnresolvedRef
from .datatypes import Opaque, Rational, SMPTELabel
from .file import MDBFile, open_mdb as open
from .mobid import MobID, ShortUID
from .objects import *  # noqa: F401,F403 -- the OMF class vocabulary
from .objects import __all__ as _object_names
from .validate import Finding, validate

__version__ = "0.1.0"

__all__ = [
    "open", "MDBFile",
    "BentoContainer", "ContainerLabel", "TOCEntry",
    "BentoError", "NotABentoContainer", "CorruptContainer",
    "MDBObject", "PropertyDef", "UnresolvedRef",
    "MobID", "ShortUID",
    "Opaque", "Rational", "SMPTELabel",
    "validate", "Finding",
    "__version__",
] + list(_object_names)
