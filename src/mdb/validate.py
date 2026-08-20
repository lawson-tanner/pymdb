"""Integrity checks.

Every check here holds in both reference samples, which is what makes them
useful: a deviation is a corruption signal, not a quirk.  The most valuable
is heap tiling -- in a healthy file the region in front of the TOC is 100%
covered by TOC-referenced values with no gaps and no overlaps, so a gap means
data nothing points at and an overlap means two objects claiming the same
bytes.

    >>> for finding in mdb.validate(f):
    ...     print(finding)
"""
from __future__ import annotations

from typing import Iterator, List, NamedTuple, Optional, TYPE_CHECKING

from .bento import ENTRY_SIZE, LABEL_SIZE, std
from .core import MDBObject
from .mobid import MobID

if TYPE_CHECKING:  # pragma: no cover
    from .file import MDBFile

__all__ = ["Finding", "validate", "heap_coverage"]

ERROR = "error"
WARNING = "warning"
INFO = "info"


class Finding(NamedTuple):
    """One validation result."""

    severity: str
    check: str
    message: str
    detail: Optional[object] = None

    @property
    def ok(self) -> bool:
        return self.severity == INFO

    def __str__(self):
        return "[%-7s] %-22s %s" % (self.severity, self.check, self.message)


class Region(NamedTuple):
    start: int
    end: int
    entry: object


def heap_coverage(container) -> "tuple[List[Region], List[tuple], List[tuple]]":
    """Tile the value heap and report ``(regions, gaps, overlaps)``.

    Geometry properties (the TOC object, the container itself) are excluded:
    they describe file regions rather than heap allocations.
    """
    regions = sorted(
        (Region(e.value, e.value + e.length, e)
         for e in container.entries
         if not e.immediate and e.length > 0
         and e.property_id not in std.GEOMETRY_PROPERTIES),
        key=lambda r: (r.start, r.end))

    gaps, overlaps = [], []
    cursor = 0
    for region in regions:
        if region.start > cursor:
            gaps.append((cursor, region.start))
        elif region.start < cursor:
            overlaps.append((region.start, min(cursor, region.end), region.entry))
        cursor = max(cursor, region.end)

    heap_end = container.label.toc_offset
    if cursor < heap_end:
        gaps.append((cursor, heap_end))
    return regions, gaps, overlaps


def validate(f: "MDBFile", deep: bool = True) -> List[Finding]:
    """Run every check and return the findings, worst first.

    ``deep=False`` skips the whole-file passes (heap tiling, reference
    resolution) for a fast structural check on a large database.
    """
    findings: List[Finding] = list(_structural(f))
    if deep:
        findings.extend(_heap(f))
        findings.extend(_references(f))
        findings.extend(_semantic(f))
    order = {ERROR: 0, WARNING: 1, INFO: 2}
    findings.sort(key=lambda x: order.get(x.severity, 3))
    return findings


# --------------------------------------------------------------------------
def _structural(f: "MDBFile") -> Iterator[Finding]:
    c = f.container
    lab = c.label

    if lab.toc_size % ENTRY_SIZE:
        yield Finding(ERROR, "toc-size",
                      "TOC size 0x%x is not a multiple of %d" % (lab.toc_size, ENTRY_SIZE))
    else:
        yield Finding(INFO, "toc-size", "%d entries of %d bytes" % (lab.entry_count, ENTRY_SIZE))

    expected = lab.toc_offset + lab.toc_size + LABEL_SIZE
    if expected != c.size:
        yield Finding(ERROR, "toc-geometry",
                      "TOC does not end at the label: 0x%x != 0x%x" % (expected, c.size))
    else:
        yield Finding(INFO, "toc-geometry", "TOC ends exactly at the container label")

    if lab.major != 1 or lab.minor != 0:
        yield Finding(WARNING, "bento-version",
                      "container version %d.%d -- only 1.0 has been characterised"
                      % (lab.major, lab.minor))
    if not lab.little_endian:
        yield Finding(WARNING, "byte-order",
                      "big-endian ('MM') container -- permitted by Bento but never observed")

    bad_immediate = [e for e in c.entries if e.immediate and e.length > 4]
    if bad_immediate:
        yield Finding(ERROR, "immediate-length",
                      "%d immediate entries claim more than 4 bytes" % len(bad_immediate),
                      bad_immediate[:8])
    else:
        yield Finding(INFO, "immediate-length", "every immediate value is <= 4 bytes")

    heap_end = lab.toc_offset
    out_of_range = [e for e in c.entries
                    if not e.immediate and e.length > 0
                    and e.property_id not in std.GEOMETRY_PROPERTIES
                    and (e.value < 0 or e.value + e.length > heap_end)]
    if out_of_range:
        yield Finding(ERROR, "value-range",
                      "%d values fall outside the heap [0, 0x%x)" % (len(out_of_range), heap_end),
                      out_of_range[:8])
    else:
        yield Finding(INFO, "value-range", "every value lies inside the heap")

    if not c.names:
        yield Finding(ERROR, "schema", "no schema names resolved -- the TOC is unreadable")
    else:
        yield Finding(INFO, "schema", "%d schema names resolved" % len(c.names))

    collisions = {k: v for k, v in c.all_names.items() if len(set(v)) > 1}
    if collisions:
        yield Finding(WARNING, "schema-collision",
                      "%d IDs bind more than one name; the last is used" % len(collisions),
                      {hex(k): v for k, v in list(collisions.items())[:8]})

    generations = {e.generation for e in c.entries}
    if generations - {1}:
        yield Finding(INFO, "generations",
                      "generation counters other than 1 present: %s -- "
                      "uncharacterised territory" % sorted(generations))


def _heap(f: "MDBFile") -> Iterator[Finding]:
    c = f.container
    _regions, gaps, overlaps = heap_coverage(c)
    heap_end = c.label.toc_offset

    if overlaps:
        total = sum(end - start for start, end, _ in overlaps)
        yield Finding(ERROR, "heap-overlap",
                      "%d overlapping values (%d bytes claimed twice)" % (len(overlaps), total),
                      [(hex(s), hex(e)) for s, e, _ in overlaps[:8]])
    else:
        yield Finding(INFO, "heap-overlap", "no value overlaps another")

    slack = [g for g in gaps if g[1] - g[0] > 0]
    if slack:
        total = sum(end - start for start, end in slack)
        # a few bytes of alignment slack immediately before the TOC is normal
        only_tail = len(slack) == 1 and slack[0][1] == heap_end and total <= 8
        severity = INFO if only_tail else WARNING
        yield Finding(severity, "heap-tiling",
                      "%d unreferenced region(s), %d bytes" % (len(slack), total),
                      [(hex(s), hex(e)) for s, e in slack[:8]])
    else:
        yield Finding(INFO, "heap-tiling", "the heap is 100%% tiled by TOC values")


def _references(f: "MDBFile") -> Iterator[Finding]:
    c = f.container
    dangling = []
    for oid in c.objects:
        obj = f.object(oid)
        if obj is None:
            continue
        for ref in obj.referenced_ids():
            if ref and ref not in c.objects:
                dangling.append((oid, ref))
                if len(dangling) > 64:
                    break
    if dangling:
        yield Finding(ERROR, "dangling-refs",
                      "%d object references do not resolve" % len(dangling),
                      [(hex(a), hex(b)) for a, b in dangling[:8]])
    else:
        yield Finding(INFO, "dangling-refs", "every object reference resolves")

    bad = [e for e in f.mob_index_entries()
           if f.class_of(e.object_id) != "MOBJ"]
    if bad:
        yield Finding(ERROR, "mob-index",
                      "%d MobIndex records do not point at a MOBJ" % len(bad),
                      bad[:8])
    else:
        yield Finding(INFO, "mob-index",
                      "all %d MobIndex records resolve to mobs" % len(f.mob_index_entries()))


def _semantic(f: "MDBFile") -> Iterator[Finding]:
    head = f.header
    seam = head.container_offset_at_close
    if seam is not None:
        toc_offset = f.container.label.toc_offset
        if not 0 <= seam <= toc_offset:
            yield Finding(WARNING, "close-seam",
                          "ContainerOffsetAtClose 0x%x is outside the heap" % seam)
        else:
            yield Finding(INFO, "close-seam",
                          "ContainerOffsetAtClose = 0x%x" % seam)

    toc_at_close = head.toc_offset_at_close
    if toc_at_close is not None and toc_at_close != f.container.label.toc_offset:
        yield Finding(INFO, "toc-at-close",
                      "TOCOffsetAtClose 0x%x != live TOC 0x%x -- expected; stale in both "
                      "reference samples, semantics unknown"
                      % (toc_at_close, f.container.label.toc_offset))

    deleted = f.deleted_mobs()
    declared = head.num_del_mobs
    if deleted or declared:
        severity = INFO if declared == len(deleted) else WARNING
        yield Finding(severity, "deleted-mobs",
                      "%d mob(s) dropped from ObjectSpine; HEAD.NumDelMobs says %s"
                      % (len(deleted), declared),
                      [hex(m.object_id) for m in deleted[:8]])

    live_ids = [m.mob_id.bytes for m in f.spine_mobs
                if isinstance(m.get("OMFI:MOBJ:MobID"), MobID)]
    if len(live_ids) != len(set(live_ids)):
        yield Finding(ERROR, "mob-id-unique",
                      "%d live mobs share a MobID with another live mob"
                      % (len(live_ids) - len(set(live_ids))))
    else:
        yield Finding(INFO, "mob-id-unique", "every live mob has a distinct MobID")

    no_mobid = [m for m in f.mobs if not isinstance(m.get("OMFI:MOBJ:MobID"), MobID)]
    if no_mobid:
        yield Finding(ERROR, "mob-id",
                      "%d mobs have no readable 32-byte MobID" % len(no_mobid),
                      no_mobid[:8])

    # Classes present in the file. Split three ways, because the three mean
    # different things: a class with its own reader is fine; one that resolves
    # through the file's class dictionary is fine too, and worth reporting so
    # the gap is visible; one that resolves to neither still reads, but only
    # by OMF property name.
    from .core import MDBObject, class_for

    inherited, generic = [], []
    for four_cc in sorted(f.class_census()):
        if class_for(four_cc) is not MDBObject:
            continue
        (generic if f.class_for_id(four_cc) is MDBObject else inherited).append(four_cc)

    if inherited:
        yield Finding(INFO, "inherited-classes",
                      "%d class(es) read through the file's own class dictionary: %s"
                      % (len(inherited), ", ".join(inherited)))
    if generic:
        yield Finding(INFO, "unknown-classes",
                      "%d class(es) with no typed reader: %s"
                      % (len(generic), ", ".join(generic)))

    # A class dictionary that names a parent the file does not contain is a
    # broken metadict -- the inheritance walk cannot follow it, and Media
    # Composer would not have written it that way.
    dangling = []
    for entry in f.class_dictionary:
        parent_ref = entry.get("OMFI:CLSD:ParentClass")
        if isinstance(parent_ref, int) and entry.parent_4cc is None:
            dangling.append("%s -> 0x%x" % (entry.class_4cc, parent_ref))
    if dangling:
        yield Finding(ERROR, "class-dictionary",
                      "%d class dictionary entr(ies) name a parent that is not a"
                      " CLSD object" % len(dangling), dangling[:8])
