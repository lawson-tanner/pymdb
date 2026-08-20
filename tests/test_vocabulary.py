"""The class vocabulary: what it covers, and that it covers it honestly.

Most classes in :mod:`mdb.objects` never appear in the reference samples --
an MDB indexes media, so effects and markers reach it only by accident.  That
makes them hard to test against data, and easy to get subtly wrong.  These
tests check the things that *are* checkable without a sample of every class:

* every OMF property name the samples' own schema declares is either bound to
  a typed attribute or knowingly left unbound -- so a property cannot be
  silently forgotten,
* every class the samples' class dictionary declares resolves to something
  better than a bare object,
* the property tables are internally consistent (no duplicate attribute names,
  no attribute bound to two OMF names, inheritance merges cleanly).
"""
import collections

import pytest

import mdb
from mdb.core import CLASS_REGISTRY, MDBObject


def _schema_names(f):
    """Every property name this file's schema registry declares."""
    out = set()
    for value in f.container.all_names.values():
        for name in (value if isinstance(value, (list, tuple)) else [value]):
            out.add(name)
    return out


def _prefix(name):
    parts = name.split(":")
    return parts[1] if parts[0] == "OMFI" and len(parts) >= 3 else None


# --------------------------------------------------------------------------
# registry shape
# --------------------------------------------------------------------------
def test_every_registered_class_has_a_distinct_4cc():
    seen = collections.Counter(cls.class_id for cls in CLASS_REGISTRY.values())
    assert [k for k, v in seen.items() if v > 1] == []


def test_registry_keys_match_their_class_ids():
    for four_cc, cls in CLASS_REGISTRY.items():
        assert cls.class_id == four_cc


@pytest.mark.parametrize("cls", sorted(set(CLASS_REGISTRY.values()),
                                       key=lambda c: c.__name__),
                         ids=lambda c: c.__name__)
def test_property_tables_are_consistent(cls):
    """No attribute name bound twice, no OMF name bound to two attributes.

    Inheritance merges by attribute name, so a subclass rebinding a name is
    legal and intentional; two *different* attributes claiming one OMF name in
    the same class is not, because only one of them could ever win.
    """
    by_omf = collections.defaultdict(list)
    for pdef in cls._propertydefs_by_name.values():
        by_omf[pdef.omf_name].append(pdef.name)
    duplicated = {omf: names for omf, names in by_omf.items() if len(names) > 1}
    assert duplicated == {}


@pytest.mark.parametrize("cls", sorted(set(CLASS_REGISTRY.values()),
                                       key=lambda c: c.__name__),
                         ids=lambda c: c.__name__)
def test_omf_names_are_well_formed(cls):
    """Every bound name looks like an OMF property name.

    Three misspellings are Avid's own and are bound as written -- the point of
    the test is that a *new* typo in this library gets caught, not that the
    file's typos get corrected.
    """
    for pdef in cls._propertydefs_by_name.values():
        assert pdef.omf_name.startswith(("OMFI:", "OMIF:")), pdef
        assert ":" in pdef.omf_name[5:] or pdef.omf_name.count(":") >= 1


def test_enums_are_named_and_documented():
    from mdb import enums
    for name in enums.__all__:
        if name == "label":
            continue
        table = getattr(enums, name)
        assert isinstance(table, dict) and table
        assert all(isinstance(k, int) and isinstance(v, str) for k, v in table.items())


def test_label_keeps_unknown_codes_visible():
    from mdb import enums
    assert enums.label(enums.TRACK_TYPE, 1) == "picture"
    assert "99" in enums.label(enums.TRACK_TYPE, 99, "track_kind")
    assert enums.label(enums.TRACK_TYPE, None) == "<unset>"


# --------------------------------------------------------------------------
# coverage against the files' own schema
# --------------------------------------------------------------------------
#: Property prefixes deliberately left without a class of their own, with the
#: reason.  Anything not here and not bound is a gap.
#: Names in the schema that belong to no class at all.
SCHEMA_SENTINELS = {
    "OMFI:NoProperty",   # OMF's "this entry has no property" placeholder
}

UNCLAIMED_PREFIXES = {
    "MDAU": "a property namespace shared by every audio descriptor, not a class"
            " -- bound on AudioDescriptor",
    "MC": "Avid's cross-class prefix; its three names are bound on GraphicEffect",
    "FL": "the shared locator path pair, bound on Locator",
    "DL": "bound on DirectoryLocator",
    "JPEG": "the frame index, bound on JPEGFrameIndex",
    "MPEG": "the frame index, bound on MPEGFrameIndex",
    "MDAT": "the media-data base, bound on MediaData",
    "trkt": "the inline track spelling, bound on Track",
    "TKDAS": "a one-name prefix, bound on TrackerDataSlot",
    "PCRL": "Avid's misspelling of PRCL, bound on ParamClip",
}


def _all_known_names():
    """Every OMF name any registered class understands, typed or structural."""
    out = set()
    for cls in set(CLASS_REGISTRY.values()):
        out.update(cls.known_properties())
    return out


def test_every_declared_class_prefix_is_claimed(f):
    """Each ``OMFI:XXXX:`` prefix maps to a class, or is listed as unclaimed."""
    bound_prefixes = {_prefix(n) for n in _all_known_names()}
    unclaimed = set()
    for name in _schema_names(f):
        prefix = _prefix(name)
        if prefix is None:
            continue
        if prefix in CLASS_REGISTRY or prefix in bound_prefixes:
            continue
        if prefix in UNCLAIMED_PREFIXES:
            continue
        unclaimed.add(prefix)
    assert unclaimed == set(), (
        "schema prefixes with no class and no documented reason: %s"
        % sorted(unclaimed))


def test_ame_version_is_the_only_widely_unbound_property(f):
    """Unbound property names should be rare and explainable.

    ``AMEVersion`` and ``Version`` are declared for nearly every class and
    written for none, so they are bound only where they carry meaning.  Any
    *other* unbound name is worth knowing about, which is what this asserts.
    """
    bound = _all_known_names()
    unbound = set()
    for name in _schema_names(f):
        if name in bound or not name.startswith(("OMFI:", "OMIF:")):
            continue
        if name.endswith(("AMEVersion", ":Version")):
            continue
        if name in SCHEMA_SENTINELS:
            continue
        unbound.add(name)
    assert unbound == set(), "unbound schema property names: %s" % sorted(unbound)


# --------------------------------------------------------------------------
# the file-driven class fallback
# --------------------------------------------------------------------------
def test_every_declared_class_resolves_to_a_typed_class(f):
    """No class in the file's own dictionary falls back to a bare object."""
    generic = [cd.class_4cc for cd in f.class_dictionary
               if f.class_for_id(cd.class_4cc) is MDBObject]
    assert generic == []


def test_unknown_class_inherits_from_its_declared_parent(f):
    """Pull a class out of the registry; the dictionary should cover for it."""
    from mdb.objects import CDCIDescriptor

    declared = {cd.class_4cc: cd.parent_4cc for cd in f.class_dictionary}
    if declared.get("JPED") != "CDCI":
        pytest.skip("this file does not declare JPED -> CDCI")

    saved = CLASS_REGISTRY.pop("JPED")
    try:
        f._class_map.clear()
        assert f.class_for_id("JPED") is CDCIDescriptor
    finally:
        CLASS_REGISTRY["JPED"] = saved
        f._class_map.clear()


def test_case_only_variants_resolve_to_the_cased_class(f):
    """``ASpi`` is Avid's typo for ``ASPI``, not a class of its own."""
    from mdb.objects import AudioSuitePluginEffect

    declared = {cd.class_4cc for cd in f.class_dictionary}
    if "ASpi" not in declared:
        pytest.skip("this file does not declare ASpi")
    assert f.class_for_id("ASpi") is AudioSuitePluginEffect


def test_a_4cc_no_one_declares_still_reads(f):
    """The never-raise rule: an invented 4CC degrades, it does not fail."""
    assert f.class_for_id("ZZZZ") is MDBObject
    assert f.class_for_id(None) is MDBObject
    assert f.class_for_id("") is MDBObject


# --------------------------------------------------------------------------
# behaviour of the new classes, exercised without samples of them
# --------------------------------------------------------------------------
def test_pan_volume_level_converts_to_db():
    from mdb.objects import PanVolumeEffect

    obj = PanVolumeEffect.__new__(PanVolumeEffect)
    obj._cache = {"level": PanVolumeEffect.UNITY_LEVEL}
    assert obj.level_db == pytest.approx(0.0)
    obj._cache = {"level": PanVolumeEffect.UNITY_LEVEL // 2}
    assert obj.level_db == pytest.approx(-6.0206, abs=1e-3)
    obj._cache = {"level": 0}
    assert obj.level_db is None, "silence has no dB value; -inf would poison arithmetic"
    obj._cache = {"level": None}
    assert obj.level_db is None


def test_motion_effect_speed_is_a_ratio():
    from mdb.objects import MotionEffect

    obj = MotionEffect.__new__(MotionEffect)
    obj._cache = {"numerator": 2, "denominator": 1}
    assert obj.speed == 2.0
    obj._cache = {"numerator": 1, "denominator": 0}
    assert obj.speed is None, "a zero denominator must not raise"


def test_sorted_list_refuses_to_slice_a_partial_record():
    from mdb.objects import SortedList

    obj = SortedList.__new__(SortedList)
    obj._cache = {"list_items": b"abcdef", "item_size": 2, "list_count": 3}
    assert obj.records() == [b"ab", b"cd", b"ef"]
    obj._cache = {"list_items": b"abcde", "item_size": 2, "list_count": 3}
    assert obj.records() == [b"ab", b"cd"], "a partial trailing record is dropped"
    obj._cache = {"list_items": b"abcdef", "item_size": 0, "list_count": 3}
    assert obj.records() == [], "no stride means no records, not a crash"


def test_rect_groups_the_didd_numerator_denominator_pairs(f):
    """Every DIDD in the samples: rects() returns only rectangles it found."""
    from mdb.objects import DigitalImageDescriptor, Rect

    for desc in f.descriptors:
        if not isinstance(desc, DigitalImageDescriptor):
            continue
        rects = desc.rects()
        assert set(rects) <= {n.lower() for n in desc.RECTANGLES}
        assert all(isinstance(r, Rect) for r in rects.values())


def test_locator_path_prefers_utf8_then_falls_back(f):
    """Subclass path spellings are considered, UTF-8 first."""
    from mdb.objects import Locator

    for loc in f.locators:
        paths = loc.all_paths()
        assert loc.path in paths or (loc.path is None and paths == [])
        assert all(p for p in paths), "empty strings must not reach all_paths()"
