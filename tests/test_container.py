"""Layer 0: the container invariants a healthy MDB always satisfies.

These are exactly the checks worth automating -- every one of them holds in
the reference samples, so a failure is a corruption signal rather than a
tolerable variation.
"""
import io
import struct

import pytest

import mdb
from mdb.bento import (ENTRY_SIZE, IMMEDIATE, LABEL_SIZE, MAGIC,
                       BentoContainer, CorruptContainer, NotABentoContainer,
                       std)


def test_label_magic_and_geometry(f):
    label = f.container.label
    assert f.container.data[-LABEL_SIZE:-16] == MAGIC
    assert label.toc_size % ENTRY_SIZE == 0
    assert label.toc_offset + label.toc_size + LABEL_SIZE == f.container.size
    assert label.entry_count == len(f.container.entries)


def test_little_endian_version_one(f):
    label = f.container.label
    assert label.byte_order == b"II"
    assert (label.major, label.minor) == (1, 0)


def test_immediate_values_are_at_most_four_bytes(f):
    for entry in f.container.entries:
        if entry.immediate:
            assert entry.length <= 4, entry


def test_pointer_values_lie_inside_the_heap(f):
    heap_end = f.container.label.toc_offset
    for entry in f.container.entries:
        if entry.immediate or entry.length == 0:
            continue
        if entry.property_id in std.GEOMETRY_PROPERTIES:
            continue
        assert 0 <= entry.value, entry
        assert entry.value + entry.length <= heap_end, entry


def test_heap_is_fully_tiled(f):
    """No gaps, no overlaps -- only alignment slack in front of the TOC."""
    from mdb.validate import heap_coverage

    _regions, gaps, overlaps = heap_coverage(f.container)
    assert overlaps == []
    heap_end = f.container.label.toc_offset
    for start, end in gaps:
        assert end == heap_end, "unreferenced hole at 0x%x-0x%x" % (start, end)
        assert end - start < ENTRY_SIZE


def test_geometry_properties_describe_the_file(f):
    """Object 1's properties 4 and 5 carry the TOC and the container itself."""
    container = f.container
    entries = {e.property_id: e for e in container.entries_for(std.CONTAINER_OBJECT)}
    toc = entries[std.P_TOC_OBJECT]
    assert (toc.value, toc.length) == (container.label.toc_offset, container.label.toc_size)
    whole = entries[std.P_CONTAINER]
    assert (whole.value, whole.length) == (0, container.size)


def test_seed_and_minseed_present(f):
    container = f.container
    assert container.minseed > 0
    assert container.seed >= container.minseed


def test_schema_resolves_every_property_and_type(f):
    """Every ID used by a data entry must have a name, standard or registered."""
    container = f.container
    for entry in container.entries:
        if entry.object_id < container.minseed:
            continue
        assert not container.name_of(entry.property_id).startswith("0x"), entry
        assert not container.name_of(entry.type_id).startswith("0x"), entry


def test_object_ids_fall_in_three_ranges(f):
    container = f.container
    for object_id in container.objects:
        assert (object_id <= 0x1F
                or 0x10040 <= object_id < container.minseed
                or object_id >= container.minseed), hex(object_id)


def test_owners_are_unique(f):
    """A byte in a tiled heap belongs to exactly one entry.

    The last few bytes before the TOC are alignment slack owned by nobody,
    so the probe walks back to the final byte a value actually covers.
    """
    from mdb.validate import heap_coverage

    container = f.container
    regions, _gaps, _overlaps = heap_coverage(container)
    last_covered = max(r.end for r in regions) - 1
    for offset in (0, last_covered):
        assert len(container.owners(offset)) == 1, hex(offset)


def test_rejects_a_file_with_no_label():
    with pytest.raises(NotABentoContainer):
        BentoContainer(b"not an mdb" * 10)


def test_rejects_a_truncated_file():
    with pytest.raises(NotABentoContainer):
        BentoContainer(b"short")


def test_rejects_inconsistent_toc_geometry():
    """A label whose TOC does not end exactly at the label is corrupt."""
    label = MAGIC + struct.pack("<H2sHHII", 0, b"II", 1, 0, 999999, 24)
    assert len(label) == LABEL_SIZE
    with pytest.raises(CorruptContainer):
        BentoContainer(b"\0" * 100 + label)


def test_rejects_a_toc_size_that_is_not_a_multiple_of_the_entry_size():
    label = MAGIC + struct.pack("<H2sHHII", 0, b"II", 1, 0, 0, 25)
    with pytest.raises(CorruptContainer):
        BentoContainer(b"\0" * 100 + label)


def test_accepts_a_file_object(sample_path):
    with io.open(str(sample_path), "rb") as handle:
        container = BentoContainer.from_file(handle)
    assert container.entries
