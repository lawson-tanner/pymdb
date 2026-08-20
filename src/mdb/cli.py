"""``mdb`` -- a command line for inspecting Avid media databases.

    mdb summary   FILE            container geometry, class census, HEAD
    mdb mobs      FILE            one line per mob: name, kind, rate, path
    mdb paths     FILE            every media path the database names
    mdb obj       FILE 0x109a0    dump one object, property by property
    mdb class     FILE WINL       dump every object of one class
    mdb tree      FILE 0x10a43    walk a mob's tracks, sequences and clips
    mdb attrs     FILE 0x10a43    an object's Avid attribute tree
    mdb find      FILE "text"     which objects contain this text
    mdb owner     FILE 0x1f40     which entry wrote the byte at this offset
    mdb classes   FILE            HEAD's class dictionary (the metadict)
    mdb validate  FILE            integrity checks; exit 1 on any error
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, List, Optional

from . import __version__, validate as run_validate
from .core import MDBObject, UnresolvedRef
from .datatypes import Opaque
from .file import MDBFile
from .objects import (Attribute, AttributeList, Locator, MediaDescriptor, Mob,
                      Sequence, SourceClip, Track)


# --------------------------------------------------------------------------
def _fmt(value: Any, width: int = 60) -> str:
    if value is None:
        return "-"
    if isinstance(value, MDBObject):
        return repr(value)
    if isinstance(value, UnresolvedRef):
        return "<unresolved 0x%x>" % value.object_id
    if isinstance(value, Opaque):
        return "%s[%d] %s" % (value.type_name.split(":")[-1], len(value),
                              value.raw[:12].hex(" "))
    if isinstance(value, bytes):
        return value[:width].hex(" ")
    if isinstance(value, list):
        if len(value) > 6:
            return "[%d items] %s ..." % (len(value), ", ".join(_fmt(v, 12) for v in value[:4]))
        return "[" + ", ".join(_fmt(v, 20) for v in value) + "]"
    text = str(value)
    return text if len(text) <= width else text[:width - 1] + "…"


def _parse_id(text: str) -> int:
    return int(text, 0)


# --------------------------------------------------------------------------
def cmd_summary(f: MDBFile, args) -> int:
    s = f.summary()
    print("file            %s" % (s["path"] or "<stdin>"))
    print("size            0x%x (%d bytes)" % (s["size"], s["size"]))
    print("container       Bento %s, byte order %s" % (s["bento_version"], s["byte_order"]))
    print("TOC             @0x%x size 0x%x -- %d entries, %d objects"
          % (s["toc_offset"], s["toc_size"], s["entries"], s["objects"]))
    print("minseed / seed  0x%x / 0x%x" % (s["minseed"], s["seed"]))
    print("schema          %d names, first data entry #%s"
          % (s["schema_names"], s["first_data_entry"]))
    print("last modified   %s" % (s["last_modified"] or "<unset>"))
    print("mobs            %d" % s["mobs"])
    print()
    print("classes:")
    for name, count in sorted(s["classes"].items(), key=lambda kv: (-kv[1], kv[0])):
        print("  %-6s %6d" % (name, count))
    print()
    print("HEAD (object 1):")
    _dump_object(f, f.header, indent="  ")
    return 0


def cmd_mobs(f: MDBFile, args) -> int:
    mobs = f.mobs
    if args.name:
        needle = args.name.lower()
        mobs = [m for m in mobs if needle in (m.name or "").lower()]
    print("%-10s %-34s %-8s %-22s %s"
          % ("object", "name", "usage", "essence", "path"))
    for mob in mobs:
        desc = mob.descriptor
        paths = mob.paths()
        print("%-10s %-34s %-8s %-22s %s"
              % ("0x%x" % mob.object_id,
                 _fmt(mob.name, 34),
                 mob.usage_code_name,
                 _fmt(desc.summary() if desc else "-", 22),
                 _fmt(paths[0] if paths else "-", 70)))
    print("\n%d mob(s)" % len(mobs))
    return 0


def cmd_paths(f: MDBFile, args) -> int:
    seen = set()
    for locator in f.locators:
        for path in locator.all_paths():
            if path and path not in seen:
                seen.add(path)
                print(path)
    print("\n%d distinct path(s)" % len(seen), file=sys.stderr)
    return 0


def _dump_object(f: MDBFile, obj: MDBObject, indent: str = "") -> None:
    container = f.container
    for entry in obj.entries:
        prop = container.name_of(entry.property_id)
        type_name = container.name_of(entry.type_id)
        where = "imm" if entry.immediate else "@0x%x" % entry.value
        values = obj.values(prop)
        # values() collapses per property name; re-decode this entry alone
        from .datatypes import decode
        value = decode(type_name, container.entry_bytes(entry),
                       container.label.endian, property_name=prop)
        print("%s%-42s %-22s %-11s %s"
              % (indent, prop, type_name.split(":")[-1], where, _fmt(value)))


def cmd_obj(f: MDBFile, args) -> int:
    obj = f.object(_parse_id(args.object_id))
    if obj is None:
        print("no object %s in this file" % args.object_id, file=sys.stderr)
        return 2
    print("%r" % obj)
    _dump_object(f, obj, indent="  ")
    return 0


def cmd_class(f: MDBFile, args) -> int:
    objects = f.by_class(args.class_id)
    for obj in objects[:args.limit]:
        print("%r" % obj)
        if not args.brief:
            _dump_object(f, obj, indent="  ")
            print()
    print("%d object(s) of class %s%s"
          % (len(objects), args.class_id,
             "" if len(objects) <= args.limit else " (showing %d)" % args.limit))
    return 0


def cmd_tree(f: MDBFile, args) -> int:
    obj = f.object(_parse_id(args.object_id)) if args.object_id else None
    roots: List[MDBObject] = [obj] if obj is not None else list(f.mobs)
    for root in roots:
        _print_tree(root, "", set(), args.depth)
        print()
    return 0


def _print_tree(obj: MDBObject, indent: str, seen: set, depth: int) -> None:
    if depth < 0:
        return
    if obj.object_id in seen:
        print("%s%r  (already shown)" % (indent, obj))
        return
    seen.add(obj.object_id)
    print("%s%r" % (indent, obj))

    children: List[MDBObject] = []
    if isinstance(obj, Mob):
        children = list(obj.tracks or [])
        desc = obj.descriptor
        if desc is not None:
            children.append(desc)
    elif isinstance(obj, Track):
        comp = obj.component
        children = [comp] if isinstance(comp, MDBObject) else []
    elif isinstance(obj, Sequence):
        children = [c for c in obj if isinstance(c, MDBObject)]
    elif isinstance(obj, MediaDescriptor):
        children = list(obj.locators())

    for child in children:
        _print_tree(child, indent + "  ", seen, depth - 1)


def cmd_attrs(f: MDBFile, args) -> int:
    obj = f.object(_parse_id(args.object_id))
    if obj is None:
        print("no object %s" % args.object_id, file=sys.stderr)
        return 2
    attrs = obj.attributes if "attributes" in dir(type(obj)) else None
    attrs = getattr(obj, "attributes", None)
    if isinstance(obj, AttributeList):
        attrs = obj
    if not isinstance(attrs, AttributeList):
        print("%r has no attribute list" % obj, file=sys.stderr)
        return 2
    print("%r" % obj)
    _print_attrs(attrs, "  ", 0)
    return 0


def _print_attrs(attrs: AttributeList, indent: str, depth: int) -> None:
    if depth > 12:
        print("%s... (depth limit)" % indent)
        return
    for attr in attrs:
        value = attr.value
        if isinstance(value, AttributeList):
            print("%s%-32s %s" % (indent, attr.name, repr(value)))
            _print_attrs(value, indent + "  ", depth + 1)
        else:
            print("%s%-32s %-8s %s" % (indent, attr.name, attr.kind_name, _fmt(value)))


def cmd_find(f: MDBFile, args) -> int:
    hits = 0
    for offset, entry in f.find_bytes(args.text, limit=args.limit):
        obj = f.object(entry.object_id)
        print("@0x%-8x %-6s obj 0x%-8x %-38s (value @0x%x len %d)"
              % (offset, f.class_of(entry.object_id) or "-", entry.object_id,
                 f.container.name_of(entry.property_id), entry.value, entry.length))
        hits += 1
    if not hits:
        print("no match in the value heap", file=sys.stderr)
        return 1
    return 0


def cmd_owner(f: MDBFile, args) -> int:
    offset = _parse_id(args.offset)
    entries = f.container.owners(offset)
    if not entries:
        print("byte 0x%x is not covered by any TOC value" % offset, file=sys.stderr)
        return 1
    for entry in entries:
        print("obj 0x%-8x %-6s %-40s %-22s @0x%x len %d"
              % (entry.object_id, f.class_of(entry.object_id) or "-",
                 f.container.name_of(entry.property_id),
                 f.container.name_of(entry.type_id), entry.value, entry.length))
    return 0


def cmd_classes(f: MDBFile, args) -> int:
    """The class dictionary, and which Python class each 4CC resolves to.

    Four answers are possible per row, and the difference matters when a file
    from a newer Media Composer turns up.  *typed* means the library has a
    class for that 4CC; *alias* means the 4CC differs from a known one only in
    case, which is Avid's typo rather than a new class (the dictionary of both
    reference samples declares ``ASPI`` and ``ASpi``); *inherited* means
    neither, but the file's own dictionary named an ancestor the library does
    know; *generic* means none of those, and the object still reads -- every
    property by OMF name -- just without typed attributes.
    """
    from .core import class_for

    entries = f.class_dictionary
    census = f.class_census()
    print("HEAD.ClassDictionary -- %d declared extension classes\n" % len(entries))
    print("  %-6s %-8s %-24s %-11s %s"
          % ("CLASS", "PARENT", "PYTHON CLASS", "RESOLVED", "COUNT"))
    for cd in sorted(entries, key=lambda c: c.class_4cc or ""):
        four_cc = cd.class_4cc or "????"
        parent = cd.parent_4cc or ""
        resolved = f.class_for_id(four_cc)
        if class_for(four_cc) is not MDBObject:
            how = "typed"
        elif resolved is MDBObject:
            how = "generic"
        elif resolved.class_id and resolved.class_id.lower() == four_cc.lower():
            how = "alias"
        else:
            how = "inherited"
        count = census.get(four_cc, 0)
        print("  %-6s %-8s %-24s %-11s %s"
              % (four_cc, parent, resolved.__name__, how, count or "-"))

    declared = {cd.class_4cc for cd in entries}
    extra = sorted(set(census) - declared)
    if extra:
        print("\n  present but not declared (built-in OMF classes, which the"
              "\n  dictionary never lists):\n")
        for four_cc in extra:
            resolved = f.class_for_id(four_cc)
            print("  %-6s %-8s %-24s %-11s %s"
                  % (four_cc, "", resolved.__name__,
                     "typed" if resolved is not MDBObject else "generic",
                     census[four_cc]))
    return 0


def cmd_validate(f: MDBFile, args) -> int:
    findings = run_validate(f, deep=not args.fast)
    errors = 0
    for finding in findings:
        if finding.severity == "info" and not args.verbose:
            continue
        print(finding)
        if finding.detail is not None and args.verbose:
            print("          %s" % (finding.detail,))
        if finding.severity == "error":
            errors += 1
    errors = sum(1 for x in findings if x.severity == "error")
    warnings = sum(1 for x in findings if x.severity == "warning")
    print("\n%d error(s), %d warning(s), %d check(s) passed"
          % (errors, warnings, sum(1 for x in findings if x.severity == "info")))
    return 1 if errors else 0


# --------------------------------------------------------------------------
COMMANDS = {
    "summary": cmd_summary, "mobs": cmd_mobs, "paths": cmd_paths,
    "obj": cmd_obj, "class": cmd_class, "tree": cmd_tree, "attrs": cmd_attrs,
    "find": cmd_find, "owner": cmd_owner, "classes": cmd_classes,
    "validate": cmd_validate,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdb", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version="pymdb " + __version__)
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    def add(name, help_text):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("file", help="path to an msmMMOB.mdb")
        return p

    add("summary", "container geometry, class census and HEAD")
    p = add("mobs", "one line per mob")
    p.add_argument("-n", "--name", help="only mobs whose name contains this text")
    add("paths", "every media path the database names")
    p = add("obj", "dump one object")
    p.add_argument("object_id", help="e.g. 0x109a0")
    p = add("class", "dump every object of one class")
    p.add_argument("class_id", help="a 4CC, e.g. WINL")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--brief", action="store_true", help="one line per object")
    p = add("tree", "walk a mob's tracks, sequences and clips")
    p.add_argument("object_id", nargs="?", help="a mob; omit for every mob")
    p.add_argument("--depth", type=int, default=8)
    p = add("attrs", "an object's Avid attribute tree")
    p.add_argument("object_id")
    p = add("find", "which objects contain this text")
    p.add_argument("text")
    p.add_argument("--limit", type=int, default=50)
    p = add("owner", "which entry wrote the byte at this offset")
    p.add_argument("offset", help="e.g. 0x1f40")
    add("classes", "HEAD's class dictionary")
    p = add("validate", "integrity checks; exit 1 on any error")
    p.add_argument("--fast", action="store_true", help="skip the whole-file passes")
    p.add_argument("-v", "--verbose", action="store_true", help="show passing checks too")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    # these listings are meant to be piped into head/grep; a closed pipe is a
    # normal end to the conversation, not an error worth a traceback
    try:
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError, ValueError):  # not POSIX, or not main thread
        pass

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    try:
        f = MDBFile(args.file)
    except OSError as exc:
        print("cannot open %s: %s" % (args.file, exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print("%s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 2
    try:
        with f:
            return COMMANDS[args.command](f, args)
    except BrokenPipeError:
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
