"""Claims measured against the two reference samples.

These pin down the exact geometry and census documented for
``msmMMOB_ImportedMedia.mdb`` and ``msmMMOB_TranscodedMedia.mdb``.  They are
regression tests for the reader, not assertions about MDBs in general: a
different Media Composer build will produce different numbers.
"""
import pytest


def test_imported_geometry(imported):
    s = imported.summary()
    assert s["size"] == 78784
    assert (s["toc_offset"], s["toc_size"]) == (0x5FE0, 0xD3C8)
    assert s["entries"] == 2259
    assert s["objects"] == 978
    assert (s["minseed"], s["seed"]) == (0x109A0, 0x10A9E)
    assert s["first_data_entry"] == 778
    assert s["schema_names"] == 757


def test_transcoded_geometry(transcoded):
    s = transcoded.summary()
    assert s["size"] == 3340760
    assert (s["toc_offset"], s["toc_size"]) == (0x816E0, 0x2AE2E0)
    assert s["entries"] == 117108
    assert s["objects"] == 17622
    assert (s["minseed"], s["seed"]) == (0x109A0, 0x14C2A)
    assert s["first_data_entry"] == 778
    assert s["schema_names"] == 757


def test_imported_class_census(imported):
    census = imported.class_census()
    assert census["MOBJ"] == 8
    assert census["TRAK"] == 16
    assert census["SCLP"] == 12
    assert census["SEQU"] == 8
    assert census["FILL"] == 16
    assert census["ATTR"] == 32
    assert census["ATTB"] == 69
    assert census["MSML"] == 4
    assert census["WINL"] == 4
    assert census["CLSD"] == 34
    assert census["HEAD"] == 1


def test_transcoded_class_census(transcoded):
    census = transcoded.class_census()
    assert census["MOBJ"] == 727
    assert census["ATTB"] == 6101
    assert census["MSML"] == 449
    assert census["WINL"] == 201
    assert census["PCMA"] == 372
    assert census["MCBR"] == 138
    assert census["CLSD"] == 34


def test_schema_ids_are_identical_across_both_samples(imported, transcoded):
    """757 shared names bind to the same numeric IDs -- cacheable, not hard-codable."""
    a = {v: k for k, v in imported.container.names.items()}
    b = {v: k for k, v in transcoded.container.names.items()}
    shared = set(a) & set(b)
    assert len(shared) == 757
    assert all(a[name] == b[name] for name in shared)


def test_known_schema_ids(imported):
    names = imported.container.names
    assert names[0x1020C] == "OMFI:ObjID"
    assert names[0x1032E] == "OMFI:MOBJ:MobID"
    assert names[0x10077] == "omfi:ObjRef"
    assert names[0x1006D] == "omfi:MobIndex"
    assert names[0x102E0] == "OMFI:FL:PathNameUTF8"


def test_container_offset_at_close_marks_the_heap_seam(imported, transcoded):
    """HEAD records the boundary between object values and close-time indexes."""
    assert imported.header.container_offset_at_close == 0x1DAE
    assert transcoded.header.container_offset_at_close == 0x78606


def test_toc_offset_at_close_is_stale_in_both_samples(imported, transcoded):
    """Documented open question: it never matches the live TOC geometry."""
    for f, stale in ((imported, 0x8310), (transcoded, 0x2A9228)):
        assert f.header.toc_offset_at_close == stale
        assert f.header.toc_offset_at_close != f.container.label.toc_offset


def test_byte_zero_is_the_middle_of_a_value(imported):
    """The file has no header: offset 0 is whatever was allocated first."""
    owners = imported.container.owners(0)
    assert len(owners) == 1
    entry = owners[0]
    assert imported.class_of(entry.object_id) == "WINL"
    assert imported.container.name_of(entry.property_id) == "OMFI:FL:PathNameUTF8"
    assert entry.length == 0xA6
    # byte 0 is the start of a UNC path -- the value, not its content, is the point
    assert imported.container.entry_bytes(entry).startswith(b"\\\\")


def test_first_data_object_is_a_windows_locator(imported):
    """TOC entry #778 -- the schema/data boundary -- tags object 0x109A0 as WINL."""
    entry = imported.container.entries[778]
    assert entry.object_id == 0x109A0
    assert entry.immediate
    assert imported.container.entry_bytes(entry) == b"WINL"


def test_composition_mob_index_has_a_non_zero_trailing_word(imported, transcoded):
    """The regression this reader was written to avoid.

    Every CompositionMobs record carries the same non-zero trailing word, so a
    64-bit read of the reference yields a nonsensical object ID.
    """
    for f, expected in ((imported, 0xEB9AF958), (transcoded, 0x366F1FD8)):
        source = f.header.get("OMFI:SourceMobs")
        composition = f.header.get("OMFI:CompositionMobs")
        assert all(e.extra == 0 for e in source)
        assert composition and all(e.extra == expected for e in composition)
        assert all(f.class_of(e.object_id) == "MOBJ" for e in composition)


def test_derivation_reaches_a_windows_path(imported):
    mob = imported.mob_by_short_uid(bytes.fromhex("2a000000") + bytes(8))
    assert mob is None  # the null UID names nothing
    with_paths = [m for m in imported.mobs if m.paths()]
    assert with_paths
    assert any(p.startswith("\\\\") or p[1:3] == ":\\"
               for m in with_paths for p in m.paths())
