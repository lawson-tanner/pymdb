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
types.

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

Unknown classes and unknown types never raise. A 4CC with no typed reader
becomes a generic `MDBObject` whose properties are still readable by OMF name;
an unrecognised `omfi:*` type yields an `Opaque` wrapper around the raw bytes.
The schema evolves — a reader that raises on next year's file is not useful.

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
mdb classes   FILE            HEAD's class dictionary (the metadict)
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
