# pymdb — progress log

Reading library for Avid Media Composer `msmMMOB.mdb` media databases.
Newest entries at the top.

---

## 2026-08-20 — Session 2: the class vocabulary

**Status:** 98 typed classes (was 31), covering every class either reference
sample's schema declares. `mdb.objects` is now a package laid out like pyavb's.
359 tests green; `mdb validate` unchanged on both samples (0 errors, 1 warning).

### What changed

**`objects.py` became a package.** 900 lines in one file was already awkward
and would have been unreadable at 3,100. The split mirrors pyavb, so the two
can be read side by side:

```
src/mdb/objects/
  base.py         OMFObject, HEAD
  attributes.py   ATTR / ATTB
  locators.py     WINL, MSML, the directory locators
  descriptors.py  MDES and every essence descriptor  (23 classes)
  misc.py         links, markers, list containers, CLSD  (15)
  components.py   CPNT and its clips  (10)
  trackgroups.py  TRKG, MOBJ, TRAK, SLCT  (5)
  effects.py      TKFX, TNFX, the time warps  (12)
  parameters.py   PRIT, PRLS, FXPS, AVUP, GRFX  (6)
  trackers.py     the TKMN family  (5)
  media.py        embedded essence, which an MDB never carries  (8)
```

`__init__.py` re-exports everything, so `from mdb.objects import Mob` and
`mdb.Mob` both still work and nothing downstream changed. Import order is
strictly layered; there are no cycles.

**Property tables came from the file, not from pyavb.** The method was: census
the samples' own name registry (759 names across ~100 class prefixes), group by
prefix, then use pyavb and OMF 2.1 to *name and explain* what the file already
declared. So the coverage is complete by construction rather than by however
far down pyavb's list one got, and every bound name provably exists in these
files' schema. Where pyavb and the file disagree, the file wins and the
docstring says so.

**Two places where they disagree, both recorded in the docstrings:**

- pyavb registers `WaveDescriptor` under class ID `WAVE` and reads
  `OMFI:WAVD:Summary` from it, because the AVB container folds descriptor and
  media data into one class. The MDB schema declares both names separately —
  `WAVD` describes, `WAVE` holds essence — so both are bound, and likewise
  `AIFD`/`AIFC` and `TIFD`/`TIFF`.
- pyavb makes `MASK`, `SPED` and `REPT` subclasses of `WARP`. The MDB class
  dictionary declares only `STRB -> WARP`. They are still modelled as time
  warps here (the property sets agree and nothing dispatches on it), with the
  divergence noted.

**Unknown classes now inherit rather than degrade.** `MDBFile.class_for_id`
resolves a 4CC in three steps: the static registry; failing that, a walk up
*this file's own* `HEAD.ClassDictionary` to the nearest ancestor the library
knows; failing that, generic `MDBObject`. An unrecognised `CDCI` subclass from
a future Media Composer reads as a picture descriptor instead of a property
bag. This is what the class dictionary is *for* — the previous behaviour threw
away an answer the file had already given.

A 4CC differing from a known one only in case resolves to the cased class:
both samples declare `ASPI` **and** `ASpi`, which is Avid's typo rather than a
class. `mdb classes` now prints, per 4CC, which of the four outcomes applied
(typed / alias / inherited / generic) and how many objects of it the file has.

**`structural_properties`.** Some properties have no sensible single attribute
name because there are *n* of them: the 32 numerator/denominator components of
`DIDD`'s four rectangles, the parallel per-point columns of `PRCL` and `CTRL`,
the per-chunk columns of `ASPI`, the ten `INTL` interpolation-quality triples.
Those are read by a method (`rects()`, `control_points()`, `chunks()`) and
declared in a new `structural_properties` class attribute, merged down the MRO
like `propertydefs`. `cls.known_properties()` returns both kinds. Without this
the coverage test below could not tell "read by a method" from "forgotten".

### New tests: `tests/test_vocabulary.py` (219 of the 359)

Most of the new classes cannot be tested against data, because no sample
contains one. So the tests check what *is* checkable:

- **Every schema property name is accounted for.** For each sample, every
  `OMFI:*` name in its registry must be bound to a `PropertyDef`, listed in a
  `structural_properties`, or named in a short allow-list with a written reason
  (`AMEVersion`/`Version`, which no object writes; `OMFI:NoProperty`, a
  sentinel). This is the test that makes the coverage claim mean something —
  it fails the moment a property is missed.
- **Every prefix maps to a class**, or appears in `UNCLAIMED_PREFIXES` with the
  reason (`MDAU` is a namespace shared by five audio descriptors, not a class;
  `PCRL` is Avid's misspelling of `PRCL`).
- **Every class in the file's dictionary resolves to something typed** — the
  fallback chain, tested by pulling `JPED` out of the registry and asserting it
  comes back as `CDCIDescriptor`.
- **Property tables are internally consistent** — this caught a real duplicate,
  `RGBADescriptor` binding `OMFI:AMDL:Attributes` twice under two names.
- Behavioural edge cases where a wrong answer would be quiet:
  `PanVolumeEffect.level_db` returns `None` at silence rather than `-inf`;
  `MotionEffect.speed` returns `None` on a zero denominator;
  `SortedList.records()` drops a partial trailing record rather than
  fabricating one.

### Things learned along the way

- **The class dictionary is smaller than it looks.** 34 entries, all Avid
  extension classes. Built-in OMF classes (`MOBJ`, `SCLP`, `TRAK`, `ATTR`,
  `WINL`, `PCMA`, ...) never appear in it — they are assumed known. So the
  dictionary is not an inventory of the file's classes, and `mdb classes` now
  lists the undeclared ones separately.
- **`EQBD` is declared as a class**, which means in a Bento container the EQ
  bands are probably separate objects reached through `EQMB:AV:Bands`, not the
  inline run of values pyavb reads from the AVB byte stream.
  `EqualizerMultiBand.bands()` handles both shapes; the object form is
  `EqualizerBand`, the inline form `InlineEqualizerBand`.
- **`FXPS -> SMLS` in the dictionary**, so the old flat keyframe list is a
  fixed-stride blob (`ListItems` / `ListCount` / `ItemSize`) rather than a list
  of objects — which is why `SortedList.records()` exists and why `FXPS`
  inherits it.
- **Three more Avid typos**, bound as written alongside the known
  `CDCI:AlphaSamledWidth`: `TRAK:LockNubmer`, `ATRE:EfffectID`, and three
  `SPED` properties spelled `OMIF:` instead of `OMFI:`. Also
  `PCRL:ExtrapKind` on a `PRCL` object, and `JPED:QuantizationTables Length`
  with a space in the property name.
- **`DOMN`, `SDSL` and `USPR` are declared with no properties at all** — one
  `AMEVersion` each and nothing else. They are bound as empty classes whose
  docstrings say plainly that their purpose is unverified, rather than being
  given invented property sets.

### Still not done

Everything from Session 1 stands. Additionally:

- **None of the new classes has been seen in a file.** The property *names* are
  verified against both samples' schema; the *semantics* are pyavb's and OMF
  2.1's, and the inheritance is the file's. An `.avb` bin, or an MDB from a
  project with rendered effects, would be the way to check. The `.avb` sample
  sitting in `File Samples/` is a bin, not an MDB, so pyavb reads it and this
  library does not — but it is the obvious source of real `TKFX`, `PVOL` and
  `TMBC` objects to compare property-by-property against.
- **`INTERP_KIND`, `EXTRAP_KIND`, `PARAM_VALUE_TYPE`, `REFORMATTING_OPTION`,
  `EDGE_TYPE` and `FILM_TYPE` are all `[I]` or `[?]`** — inferred from pyavb
  and OMF, unverifiable without an object that uses them.
- **`MULD.children()` and `DIDD.next_descriptor` are untested walks.** Both
  should work; neither has ever run against data.

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
                     -- became a package in Session 2
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
