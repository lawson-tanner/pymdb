"""The validator, and the corruption it is meant to catch."""
import struct

import pytest

import mdb
from mdb.bento import ENTRY_SIZE, LABEL_SIZE
from mdb.validate import heap_coverage, validate


def _severities(findings):
    return {f.check: f.severity for f in findings}


def test_healthy_samples_produce_no_errors(f):
    findings = validate(f)
    errors = [x for x in findings if x.severity == "error"]
    assert errors == [], "\n".join(str(x) for x in errors)


def test_all_structural_checks_pass(f):
    checks = _severities(validate(f))
    for name in ("toc-size", "toc-geometry", "immediate-length", "value-range",
                 "schema", "heap-overlap", "dangling-refs", "mob-index"):
        assert checks[name] == "info", name


def test_fast_mode_skips_the_whole_file_passes(f):
    checks = _severities(validate(f, deep=False))
    assert "toc-geometry" in checks
    assert "heap-overlap" not in checks


def test_schema_collision_is_reported_as_a_warning(f):
    """Two IDs bind two names each in these files -- real, and worth flagging."""
    checks = _severities(validate(f))
    assert checks.get("schema-collision") == "warning"


def test_heap_coverage_reports_no_overlap(f):
    regions, gaps, overlaps = heap_coverage(f.container)
    assert regions
    assert overlaps == []
    assert sum(end - start for start, end in gaps) < ENTRY_SIZE


def _corrupt(f, mutate):
    data = bytearray(f.container.data)
    mutate(data, f.container)
    return bytes(data)


def test_detects_a_truncated_value(f):
    """Point a value past the end of the heap and the range check must fire."""
    container = f.container
    victim = next(e for e in container.entries
                  if not e.immediate and e.length > 8 and e.property_id > 0x1F)
    offset = container.label.toc_offset + victim.index * ENTRY_SIZE

    def mutate(data, c):
        struct.pack_into("<I", data, offset + 16, c.label.toc_offset + 0x1000)

    damaged = mdb.MDBFile(_corrupt(f, mutate))
    checks = _severities(validate(damaged))
    assert checks["value-range"] == "error"


def test_detects_a_dangling_reference(f):
    container = f.container
    victim = next(e for e in container.entries
                  if container.name_of(e.type_id) == "omfi:ObjRef" and e.immediate is False)
    offset = victim.value

    def mutate(data, c):
        struct.pack_into("<Q", data, offset, 0xDEAD)

    damaged = mdb.MDBFile(_corrupt(f, mutate))
    checks = _severities(validate(damaged))
    assert checks["dangling-refs"] == "error"


def test_detects_a_bad_immediate_length(f):
    container = f.container
    victim = next(e for e in container.entries if e.immediate)
    offset = container.label.toc_offset + victim.index * ENTRY_SIZE

    def mutate(data, c):
        struct.pack_into("<I", data, offset + 16, 99)

    damaged = mdb.MDBFile(_corrupt(f, mutate))
    checks = _severities(validate(damaged))
    assert checks["immediate-length"] == "error"


def test_a_damaged_label_fails_to_open(f):
    data = bytearray(f.container.data)
    data[-LABEL_SIZE] ^= 0xFF
    with pytest.raises(mdb.NotABentoContainer):
        mdb.MDBFile(bytes(data))


def test_findings_are_ordered_worst_first(f):
    findings = validate(f)
    rank = {"error": 0, "warning": 1, "info": 2}
    order = [rank[x.severity] for x in findings]
    assert order == sorted(order)
