# pymdb

Read Avid Media Composer `msmMMOB.mdb` media databases from Python.

`msmMMOB.mdb` is the index Media Composer keeps inside each Avid media folder
(`Avid MediaFiles/MXF/1/`, alongside `msmFMID.pmr`): one entry per media file,
with clip names, MobIDs, file paths, track structure, essence descriptors and
Avid's private attributes. Physically it is an **OMF Interchange 1.x object
database in a Bento container** — and it has no header, so the only correct way
in is the last 24 bytes of the file.

This library reads. It does not write: Media Composer updates these files in
place, so treat them as read-only evidence.

```python
import mdb

with mdb.open("Avid MediaFiles/MXF/1/msmMMOB.mdb") as f:
    print(f.summary()["classes"])

    for mob in f.spine_mobs:
        print(mob.name,
              mob.descriptor.summary() if mob.descriptor else "",
              mob.volumes(),
              mob.paths())
```

## Install

```
pip install -e .
```

No dependencies. Python 3.8+.

## Two layers

**Layer 1** — named, typed objects. `MOBJ` becomes `Mob`, `CDCI` becomes
`CDCIDescriptor`, references resolve to live objects, values decode to Python
types. Ninety-odd classes are covered — every class the reference samples'
schema declares, not just the ones they happen to contain.

```python
mob = f.spine_mobs[0]
mob.name                       # 'CLIP_NAME'
mob.mob_id                     # <MobID 060a2b34...>
mob.edit_rate                  # 25/1
mob.attribute("_PJ")           # 'PROJECT'
mob.tracks[0].component        # <SEQU Sequence ...>
mob.descriptor.stored_width    # 1920
mob.paths()                    # ['\\\\SERVER\\SHARE\\...\\clip.mxf']
mob.volumes()                  # ['VOLUME (X:)']
mob.bins()                     # ['BIN_NAME']
mob.derivation_chain()         # [master, file mob, tape mob, ...]
```

**Layer 0** — the raw container, for questions the object model does not
cover.

```python
f.container.label              # <ContainerLabel 1.0 II toc@0x5fe0 ...>
f.container.entries[778]       # <TOCEntry #778 obj=0x109a0 ...>
f.container.owners(0x1f40)     # which entry wrote the byte at this offset
f.container.names[0x1032e]     # 'OMFI:MOBJ:MobID'
```

### The class vocabulary

`mdb.objects` is a package, laid out like pyavb's: `components`,
`trackgroups`, `effects`, `descriptors`, `locators`, `attributes`,
`parameters`, `trackers`, `media`, `misc`. Everything is re-exported, so
`from mdb.objects import Mob` and `mdb.Mob` both work.

Most of those classes never appear in the reference samples, and that is the
expected result rather than a gap: an MDB indexes media files, so it is full of
mobs, descriptors and locators, and contains an effect or a marker only if
something unusual has happened. They are defined because the samples' *schema*
declares them — 759 property names across roughly a hundred class prefixes —
so a file that does use one reads as a typed object rather than as a bag of
names. Where a class's behaviour could not be checked against data, its
docstring says so.

### Unknown classes degrade, they never raise

Three fallbacks, in order:

1. A 4CC the library knows resolves to its class.
2. A 4CC it does not know is looked up in **this file's own
   `HEAD.ClassDictionary`**, and the nearest declared ancestor the library
   *does* know is used instead. An unrecognised `CDCI` subclass from a future
   Media Composer still reads as a picture descriptor. This is the whole
   reason the class dictionary is in the file; ignoring it would be throwing
   away an answer the file already gave.
3. Failing both, a generic `MDBObject` — every property still readable by OMF
   name, just without typed attributes.

An unrecognised `omfi:*` type yields an `Opaque` wrapper around the raw bytes.
The schema evolves — a reader that raises on next year's file is not useful.

`mdb classes FILE` prints which of the three applied to every class in the
file.

## Command line

```
mdb summary   FILE            container geometry, class census, HEAD
mdb mobs      FILE            one line per mob: name, kind, essence, path
mdb paths     FILE            every media path the database names
mdb obj       FILE 0x109a0    dump one object, property by property
mdb class     FILE WINL       dump every object of one class
mdb tree      FILE 0x10a43    walk a mob's tracks, sequences and clips
mdb attrs     FILE 0x10a43    an object's Avid attribute tree
mdb find      FILE "TEXT"     which objects contain this text
mdb owner     FILE 0x1f40     which entry wrote the byte at this offset
mdb classes   FILE            HEAD's class dictionary, and how each 4CC resolves
mdb validate  FILE            integrity checks; exit 1 on any error
```

`mdb validate` is the one to reach for when a database is suspect. Every check
holds in known-good files, so a failure is a corruption signal rather than a
tolerable variation — heap tiling especially: in a healthy MDB the region in
front of the TOC is 100% covered by TOC-referenced values, with no gaps and no
overlaps.

## The format in one screen

```
offset 0  +---------------------------------------------+
          | VALUE HEAP                                  |
          |   object property values (allocation order) |
          |   close-time HEAD indexes                   |
          |   schema name strings                       |
          +---------------------------------------------+
          | TOC -- N x 24-byte entries                  |
          |   (object, property, type, value, len, gen) |
 EOF-24   +---------------------------------------------+
          | CONTAINER LABEL -- magic, TOC offset/size   |
 EOF      +---------------------------------------------+
```

Read the label, read the TOC, group entries by object ID, resolve property and
type IDs to names through the file's own registry, and every entry becomes
readable. An object has no physical record: it *is* the set of entries sharing
an ID. Values of four bytes or fewer live inside the entry; anything larger is
an offset into the heap.

Three ID ranges tell you what a number means: `0x01`–`0x1F` are Bento standard
IDs, `0x10040`–`minseed` are the schema registry, and everything from `minseed`
up is content.

## Notes from the samples

Findings that cost time to discover, recorded so they do not have to be
rediscovered:

- **The `MobIndex` object reference is 32-bit, not 64-bit.** Each 20-byte
  record is a 12-byte short UID, a `uint32` object ID and a further `uint32`.
  That last word is zero throughout `SourceMobs` and a constant non-zero value
  throughout `CompositionMobs`, so a 64-bit read silently corrupts every
  composition-mob lookup. Its meaning is unknown; it is preserved as
  `MobIndexEntry.extra`.
- **A MobID is unique across *live* mobs only.** Deleting a mob unlinks it from
  `HEAD.ObjectSpine` and from every other object but leaves its TOC entries in
  place, still carrying the MobID of its live twin. `HEAD.NumDelMobs` counts
  these exactly. Use `f.spine_mobs` for the authoritative list and
  `f.deleted_mobs()` for the leftovers.
- **Two UMID label variants occur**, differing at label bytes 7 and 11
  (material generation `0x10` on most mobs, `0x00` on tape-side source mobs).
  Both are valid SMPTE 330M.
- **`MDES:Locator` is an `ObjRefArray`**, not a single reference, and `MSML` is
  a locator subclass — so a descriptor's locator list mixes file paths (`WINL`)
  with volume links (`MSML`).
- **`MCBR` carries no MobID.** Bin membership is reached through the attribute
  tree: `MOBJ -> CPNT:Attributes -> ATTR -> ATTB('_ORG_BIN') -> MCBR`.
- **Properties repeat.** `MOBJ:MobID` is written twice with identical content,
  a `WINL` can carry two different `FL:PathNameUTF8` values, and
  `DIDD:VideoLineMap` is genuinely multi-valued. Attribute access returns the
  last; `obj.values(name)` returns all of them.
- **Two schema IDs bind two names each** (`0x10994`, `0x10995` — `ASPI` and
  `FXPS` names collide). `validate` reports this as a warning.
- **The class dictionary declares both `ASPI` and `ASpi`.** A 4CC differing
  from a known one only in case is Avid's typo, not a new class, and is
  resolved to the cased one.
- **Descriptor and media-data classes are separate in OMF** and the MDB schema
  declares both: `WAVD` describes, `WAVE` holds the essence; likewise
  `AIFD`/`AIFC` and `TIFD`/`TIFF`. pyavb folds each pair together under the
  data-class name because the AVB container does. This library keeps them
  apart, because these files do.
- **`DIDD` carries four exact-rational rectangles** — valid, essence, source
  and framing — each as eight numerator/denominator properties.
  `descriptor.rects()` groups them back up.
- **Avid's typos are bound as written**, because that is what the file says:
  `CDCI:AlphaSamledWidth`, `TRAK:LockNubmer`, `PCRL:ExtrapKind` (for `PRCL`),
  `ATRE:EfffectID`, and three `SPED` properties spelled `OMIF:` rather than
  `OMFI:`.
- **`TOCOffsetAtClose` never matches the live TOC geometry** in any sample seen
  so far. Suspected stale breadcrumb from an earlier save; a candidate
  dirty-close detector, but unconfirmed.

## Testing

```
pip install -e ".[test]"
pytest
```

Tests run against real Media Composer output. Put `.mdb` files in
`tests/samples/`, or point `PYMDB_SAMPLES` at a directory of them; the
structural tests still run without samples, and sample-dependent tests skip
cleanly.

## References

- *Bento Specification 1.0d5*, Harris & Ruben, Apple — the container layer.
- *OMF Interchange Specification 2.1* — object semantics. Note that MDB uses
  OMF **1.x** property naming (`OMFI:CLSD:*`).
- [pyavb](https://github.com/markreidgfx/pyavb) — the same Avid class and
  attribute vocabulary in the `.avb` bin container. Different container,
  identical semantics; the best reference for what an attribute means.
- *AAF Object Specification 1.1* — UMID structure and SMPTE labels.

## Licence

MIT.
