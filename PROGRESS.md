# pymdb — progress log

Reading library for Avid Media Composer `msmMMOB.mdb` media databases.
Newest entries at the top.

---

## 2026-08-19 — Session 1: first working reader

**Status:** Layer 0 and Layer 1 complete for everything present in the two
reference samples. CLI, validator and 140-test suite all green. Read-only.

### What exists now

```
Work/pymdb/
  src/mdb/
    __init__.py      public API; `mdb.open(path)`
    bento.py         Layer 0 — container label, TOC, objects, schema registry
    datatypes.py     omfi:* value decoders, SMPTE label unswap, Opaque fallback
    mobid.py         MobID (32-byte UMID) and ShortUID (12-byte OMF1)
    enums.py         AttrKind, TrackType, PhysicalMobType, UsageCode, ... 
    core.py          Layer 1 base — MDBObject, PropertyDef, class registry
    objects.py       31 typed OMF/Avid classes (HEAD, MOBJ, TRAK, CDCI, ...)
    file.py          MDBFile — indexes, lookups, searches, summary
    validate.py      integrity checks (13 of them)
    cli.py           `mdb` command, 11 subcommands
  tests/             140 tests across 5 modules
  examples/          inventory.py
  pyproject.toml     packaging; console script `mdb`
  README.md
```

### Design decisions

**Two layers, deliberately.** Layer 0 (`BentoContainer`) is a faithful,
OMF-agnostic reader of the container: label, TOC entries, object grouping, name
registry, `owners(offset)`. Layer 1 puts named classes and typed properties on
top. The split matters because corruption triage lives at Layer 0 — "which
entry owns byte 0x1f40?" is unanswerable from an object model — while everyday
use lives at Layer 1.

**Decoding is driven by the file, not by tables.** Every TOC entry names its
type, and the file's own schema registry resolves that number to a name. So the
decoder dispatches on `omfi:ObjRefArray`, never on a hard-coded property ID.
The briefing document notes the schema is stable per Media Composer generation;
that makes it cacheable, not hard-codable, and the code re-derives it per file.

**Nothing raises on unknown input.** An unrecognised 4CC yields a generic
`MDBObject` with every property readable by OMF name; an unrecognised `omfi:*`
type yields `Opaque` holding the raw bytes. Media Composer adds classes between
releases and a reader that raises on them is a reader that breaks.

**Duplicate properties are first-class.** `obj.name` gives the last value;
`obj.values("OMFI:...")` gives all of them. This is not defensive coding — the
format genuinely writes `MOBJ:MobID` twice and `DIDD:VideoLineMap` once per
field.

### Corrections to the briefing document

Empirical work turned up five places where the briefing (`MDB_Format_101.md` /
`MDB_Structural_Blueprint.md`) is wrong or incomplete. All were verified across
both samples.

1. **`omfi:MobIndex` object references are 32-bit, not 64-bit.** The record is
   `12-byte short UID + uint32 objectID + uint32 extra`. `extra` is zero for
   every `SourceMobs` record — which is why reading a `uint64` appeared to work
   — and a constant non-zero value for every `CompositionMobs` record
   (`0xEB9AF958` in ImportedMedia, `0x366F1FD8` in TranscodedMedia). Reading 64
   bits corrupts all 139 composition-mob lookups. The reference parser
   `mdbparse.py` has this bug. Meaning of `extra`: unknown **[?]** — it occurs
   only inside the MobIndex, once per record, and appears nowhere else in the
   file.

2. **`OMFI:SCLP:SourceID` is a full 32-byte UMID, not a 12-byte short UID.**
   Every `omfi:UID` value in both samples is 32 bytes. The 12-byte short UID
   appears only inside `MobIndex` records.

3. **`OMFI:MDES:Locator` is an `omfi:ObjRefArray`, not an `omfi:ObjRef`**, and
   `MSML` is a *locator* subclass (`MSML -> TXTL` in the class dictionary). A
   descriptor's locator list therefore mixes `WINL` file paths with `MSML`
   volume links. The briefing's "descriptor -> MDES:Locator -> WINL" walk is
   right but under-describes the shape.

4. **`MCBR` does not join by MobID.** It has no MobID property at all (census:
   `binID.high`, `binID.low`, `binName`, `binNameUTF8`, `AMEVersion`,
   `MinorVersion`). Bin membership is reached through the attribute tree:
   `MOBJ -> CPNT:Attributes -> ATTR -> ATTB('_ORG_BIN', kind=object) -> MCBR`.
   Same for `MCMR`. Only `MSML` genuinely carries a MobID copy.

5. **MobIDs are not unique across `MOBJ` objects** — see the finding below.

### New findings

**`HEAD.NumDelMobs` counts orphaned mob objects — open question resolved.**
Both samples report `NumDelMobs = 4`, and both contain exactly 4 `MOBJ` objects
that are absent from `HEAD.ObjectSpine` and referenced by nothing at all. Each
orphan duplicates the MobID, name and track count of a live mob. So: deleting a
mob unlinks it from the spine and from the object graph, but leaves its TOC
entries and heap values in place; `NumDelMobs` is the count of those leftovers,
and `DelBlobsSize = 0` is consistent with no heap space having been reclaimed.

Practical consequence: `HEAD.ObjectSpine` is the authoritative mob list. A
naive `by_class('MOBJ')` scan returns deleted mobs too, and MobID lookup is
ambiguous unless you prefer the live twin. Exposed as `f.spine_mobs`,
`f.deleted_mobs()`, `f.mobs_by_id()`; `f.mob_by_id()` prefers the live mob.

**Two UMID label variants.** `06 0a 2b 34 01 01 01 05 01 01 0f 10` on 650 mobs
and `06 0a 2b 34 01 01 01 00 01 01 0f 00` on 77 in TranscodedMedia — the latter
exactly the tape-side source mobs of the 77 video clips. Bytes 7 and 11 are the
SMPTE specification version and material generation method, so both are valid
330M UMIDs. A prefix equality check against one variant rejects legitimate
mobs.

**`omfi:AttrKind` 4 = "bob" blob — inferred value confirmed.** Kind 4
co-occurs with `ATTB:BobData` + `ATTB:BobSize` and with no `*Attribute`
property, in 255 cases across both samples. Kinds 1/2/3 confirmed as
int/string/object by the same co-occurrence test. The briefing tagged this
**[I]**; it is now **[V]**.

**`omfi:GUID` is an AAF half-swapped AUID.** Stored as
`{uint32 Data1; uint16 Data2; uint16 Data3; uint8 Data4[8]}` with the halves
exchanged, which is why the `06 0e 2b 34` prefix turns up at byte 8.
`SMPTELabel.ul` restores canonical order; `DIDD:EssenceCompression` then reads
as a recognisable MXF picture-coding label.

**Type census beyond the briefing's table.** Types present that the briefing
does not list: `omfi:Rational`, `omfi:Int64`, `omfi:TrackType`,
`omfi:UsageCodeType` (4 bytes, not 2), `omfi:PhysicalMobType`,
`omfi:ColorSitingType`, `omfi:LayoutType`, `omfi:VersionType`,
`omfi:Int32Array`, `omfi:CharSetType`, `omfi:EdgeType`, `omfi:JPEGTableIDType`.
`OMFI:ByteOrder` is declared `omfi:Short` but reads as ASCII `II` — decoded per
property rather than per type.

**Schema name collisions are real.** Objects `0x10994` and `0x10995` each bind
two different names (`OMFI:ASPI:tracksToAffect` / `OMFI:FXPS:ccNumParams`, and
`OMFI:ASPI:renderingMode` / `OMFI:FXPS:colorCorrection`). Both bindings are
kept (`container.all_names`); the last wins for display. `validate` reports it
as a warning.

### Verified against both samples

Everything the briefing tags **[V]** reproduces: container geometry, TOC entry
counts, first data entry at #778, minseed/seed, 757 schema names binding to
identical IDs in both files, class census, `ContainerOffsetAtClose` marking the
heap seam exactly, `TOCOffsetAtClose` being stale in both, byte 0 belonging to
a `WINL` path string, and the heap tiling with no gaps or overlaps beyond a few
bytes of alignment slack before the TOC.

`mdb validate` on both samples: 0 errors, 1 warning (the schema collision),
13 checks passed. Full deep validation of the 3.3 MB / 117,108-entry sample
takes 0.35 s.

### Not done yet

- **Writing.** Out of scope for now, and genuinely risky: Media Composer
  updates these files in place.
- **Classes declared in the class dictionary but absent from the samples** —
  `MDTP`, `JPED`, `MPGI`, `TNFX`, `TKFX`, `PVOL`, `EQMB`, `ASPI`, `STRB`,
  `FXPS`, `DOML`, `TMCS`, `TMBC`, `LITM`, `TKMN`, `TKPS`, `TKDS`, `TKPA`,
  `TKDA`, `EQBD`. They will read as generic objects. pyavb has property
  vocabulary for most of these; worth porting when a sample turns up.
- **`msmFMID.pmr`** — the sibling file. Almost certainly not Bento; unverified.
  Checking its last 24 bytes is a one-line test.
- **A dirty sample.** Every open question about generation counters,
  `TOCOffsetAtClose` and the deletion bookkeeping needs an MDB from a crashed
  or heavily edited session. Worth collecting one.
- **Cross-version schema stability.** Both samples come from the same Media
  Composer generation. The reader re-derives the schema per file so this is
  safe, but the reference-sample tests will not hold on other builds.
- **Performance.** Adequate (0.35 s deep-validating 3.3 MB) but the whole file
  is read into memory and `by_class` builds a full index. Fine for MDBs; would
  need revisiting only for pathologically large ones.

### Open questions carried forward

- What is the `MobIndex` trailing `uint32`? Constant per file, non-zero only on
  `CompositionMobs`.
- Why is `MOBJ:MobID` written twice with identical content?
- What does `TOCOffsetAtClose` actually record?
- Full `omfi:UsageCodeType` enum — 0, 1 and 7 observed; Avid publishes no table.
- The 5-byte `omfi:TimeStamp` trailing byte (all-zero in both samples).
