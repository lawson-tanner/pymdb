# pymdb

Read Avid Media Composer `msmMMOB.mdb` media databases from Python.

`msmMMOB.mdb` is the index Media Composer keeps inside each Avid media folder
(`Avid MediaFiles/MXF/1/`, alongside `msmFMID.pmr`): one entry per media file,
with clip names, MobIDs, file paths, track structure, essence descriptors and
Avid's private attributes.

This library reads. It does not write: Media Composer updates these files in
place, so treat them as read-only evidence.

## Install

```
pip install -e .
```

No dependencies. Python 3.8+.

## Quick start

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

`mdb.open()` accepts a path, an open file object, or raw `bytes`. Always use
it as a context manager (or call `f.close()` yourself) — it drops the cached
object graph on exit.

Objects are built lazily and cached, so opening a multi-megabyte database
costs only the container parse; reading a handful of mobs never touches the
other thousands of objects in the file.

## The object model

Every object comes back as a typed Python class chosen from its 4CC:
`MOBJ` → `Mob`, `CDCI` → `CDCIDescriptor`, `WINL` → `WindowsLocator`, and so
on. References resolve to live objects automatically, and values decode to
native Python types (`int`, `str`, `datetime`, `Fraction`-like `Rational`,
lists, nested objects).

Read a property three ways, in increasing order of rawness:

```python
mob.name                        # typed attribute — resolved, decoded, cached
mob["OMFI:CPNT:Name"]           # by OMF property name — raises if absent
mob.get("OMFI:CPNT:Name")       # by OMF property name — None if absent
mob.values("OMFI:MOBJ:MobID")   # every value written for this name, in file order
```

Prefer the typed attribute when one exists; fall back to `get`/`values` for
properties this library hasn't given a friendly name yet, or when you need
every value a repeated property carries rather than just the last one.

**Unknown classes never raise.** A 4CC this library doesn't recognise still
reads: it resolves to the nearest ancestor class the file's own metadata
declares, or failing that to a generic object with every property still
readable by OMF name. A database from a newer Media Composer version will
open and read cleanly even if this library predates it. Run `mdb classes
FILE` to see how every class in a given file resolved.

## Common tasks

**Find a mob by name and inspect it:**

```python
mob = next(m for m in f.spine_mobs if m.name == "CLIP_NAME")
mob.mob_id                     # MobID
mob.edit_rate                  # Rational, e.g. 25/1
mob.usage_code_name            # 'Usage_SubClip', etc.
mob.attribute("_PJ")           # project name, from Avid's attribute tree
mob.tracks[0].component        # the track's top-level component
```

**Get every file path and volume a mob's media is known by:**

```python
mob.paths()                    # ['\\\\SERVER\\SHARE\\...\\clip.mxf']
mob.volumes()                  # ['VOLUME (X:)']
mob.bins()                     # ['BIN_NAME'] — which .avb bins reference it
```

**Build an inventory of everything in the database** (see also
`examples/inventory.py`, which does this as a CSV export):

```python
for mob in f.spine_mobs:
    d = mob.descriptor
    print(mob.name, d.summary() if d else "no descriptor", mob.paths())
```

**Trace where a clip's media came from:**

```python
mob.sources()                  # immediate previous-generation mobs
mob.derivation_chain()         # walked all the way back, master first
```

**Look up a mob by MobID** (e.g. from a `.avb` bin, or from `SCLP:SourceID`):

```python
f.mob_by_id("060a2b34...")             # full 32-byte UMID, as hex or MobID
f.mob_by_short_uid(some_short_uid)     # 12-byte short UID
```

**Search for text anywhere in the file** (a path fragment, a clip name):

```python
f.find("PROJECT_NAME")         # every object whose values contain this text
```

**List every object of one class, or get a quick class census:**

```python
f.by_class("WINL")             # every WindowsLocator
f.class_census()               # Counter({'ATTB': 4210, 'MOBJ': 1830, ...})
```

**Check a database's integrity** before trusting it:

```python
from mdb import validate
findings = validate(f)
errors = [x for x in findings if x.severity == "error"]
```

Prefer the CLI (`mdb validate FILE`) for this in practice — see below.

**Drop down to the raw container** for anything the object model doesn't
cover, such as "what wrote this byte":

```python
f.container.owners(0x1f40)     # which TOC entries cover this byte offset
f.object(0x109a0)              # any object, by its raw object ID
```

## Things worth knowing

- **A mob has no properties of its own except through its class.** `Mob`
  extends `TrackGroup` extends `Component`, so `mob.tracks`, `mob.attributes`
  and `mob.name` are all inherited, not `Mob`-specific — this is true of the
  whole class hierarchy, and mirrors how the format itself layers classes.
- **`f.mobs` includes deleted mobs; `f.spine_mobs` doesn't.** Use
  `spine_mobs` unless you specifically want deleted ones (`f.deleted_mobs()`).
  A deleted mob keeps the MobID of its live twin, so MobIDs are only unique
  across live mobs.
- **Some properties are genuinely repeated** (paths, video line maps). Typed
  attribute access always gives you the last value; call `.values(name)` if
  you need all of them.
- **Bin membership doesn't have a MobID to match on** — `mob.bins()` and
  `mob.bin_links()` walk the Avid attribute tree rather than doing a direct
  lookup, which is why they're methods rather than simple properties.

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

`mdb validate` is the one to reach for when a database is suspect — every
check holds in known-good files, so a failure is a corruption signal, not a
tolerable variation. Use `-v` to also see the checks that passed, `--fast` to
skip the whole-file passes.

`mdb mobs FILE -n TEXT` filters to mobs whose name contains `TEXT`.
`mdb class FILE WINL --brief` lists one line per object instead of a full
dump; `--limit N` caps how many are shown.

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

- [pyavb](https://github.com/markreidgfx/pyavb) — the same Avid class and
  attribute vocabulary in the `.avb` bin container. Different container,
  identical semantics; the best reference for what an attribute means.
- *OMF Interchange Specification 2.1* and *Bento Specification 1.0d5* —
  the underlying formats, if you need to go past what this library exposes.

## Licence

MIT.
