pymdb
=====

Read Avid Media Composer ``msmMMOB.mdb`` media databases from Python.

An MDB is the index Media Composer keeps inside each Avid media folder: one
entry per media file, with clip names, MobIDs, paths, track structure and
essence descriptors. Physically it is an OMF Interchange 1.x object database
in a Bento container. This library reads; it does not write.

.. code-block:: python

   import mdb

   with mdb.open("Avid MediaFiles/MXF/1/msmMMOB.mdb") as f:
       print(f.summary()["classes"])
       for mob in f.spine_mobs:
           print(mob.name, mob.descriptor.summary() if mob.descriptor else "",
                 mob.paths())

Two layers are available: :class:`~mdb.file.MDBFile` gives named, typed
objects; :class:`~mdb.bento.BentoContainer` underneath gives the raw TOC for
questions the object model does not cover.

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/mdb
   api/file
   api/bento
   api/core
   api/datatypes
   api/mobid
   api/validate
   api/enums
   api/objects
   api/cli

Indices
-------

* :ref:`genindex`
* :ref:`modindex`
