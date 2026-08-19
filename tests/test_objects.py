"""Layer 1: the object model, and the walks a user actually performs."""
import pytest

import mdb
from mdb.core import UnresolvedRef
from mdb.mobid import MobID, ShortUID
from mdb.objects import (Attribute, AttributeList, BinLink, ClassDescriptor,
                         Header, Locator, MediaDescriptor, MediaStreamLink,
                         Mob, Sequence, SourceClip, Track)


def test_header_is_object_one(f):
    head = f.header
    assert isinstance(head, Header)
    assert head.object_id == 1
    assert head.class_name == "HEAD"
    assert head.byte_order == "II"


def test_header_carries_both_layers(f):
    """Object 1 is Bento's container object and OMFi's HEAD at once."""
    head = f.header
    assert head.object_spine, "HEAD must list its mobs"
    assert head.class_dictionary, "HEAD must carry a class dictionary"
    assert "<std:seed>" in [f.container.name_of(e.property_id) for e in head.entries]


def test_object_spine_holds_the_live_mobs(f):
    """The spine is the authoritative list; deleted mobs linger outside it.

    Deleting a mob unlinks it from the spine but leaves its object in the
    container, and ``HEAD.NumDelMobs`` counts exactly those leftovers.
    """
    spine_ids = {m.object_id for m in f.spine_mobs}
    all_ids = {m.object_id for m in f.mobs}
    assert spine_ids <= all_ids
    deleted = f.deleted_mobs()
    assert {m.object_id for m in deleted} == all_ids - spine_ids
    assert len(deleted) == f.header.num_del_mobs


def test_deleted_mobs_are_unreferenced(f):
    """Nothing points at a deleted mob -- that is what makes it deleted."""
    for mob in f.deleted_mobs():
        assert f.referrers(mob.object_id) == []


def test_every_mob_has_a_full_umid(f):
    """Two label variants occur -- both are valid SMPTE 330M UMIDs.

    Most mobs use material generation 0x10; the tape-side source mobs use
    0x00, differing at label bytes 7 and 11.
    """
    generations = set()
    for mob in f.mobs:
        assert isinstance(mob.mob_id, MobID), mob
        assert mob.mob_id.is_smpte_umid, mob.mob_id.hex()
        generations.add(mob.mob_id.material_generation)
    assert generations <= {0x00, 0x10}


def test_live_mob_ids_are_unique(f):
    """Unique across *live* mobs only: a deleted mob keeps its twin's MobID."""
    ids = [m.mob_id.bytes for m in f.spine_mobs]
    assert len(ids) == len(set(ids))


def test_a_shared_mob_id_resolves_to_the_live_mob(f):
    live = {m.object_id for m in f.spine_mobs}
    for mob in f.deleted_mobs():
        candidates = f.mobs_by_id(mob.mob_id)
        if len(candidates) > 1:
            assert f.mob_by_id(mob.mob_id).object_id in live


def test_mob_lookup_round_trips(f):
    for mob in f.mobs:
        assert f.mob_by_id(mob.mob_id) is not None
        assert f.mob_by_short_uid(mob.mob_id.short_uid).mob_id == mob.mob_id


def test_mob_index_records_resolve_to_mobs(f):
    entries = f.mob_index_entries()
    assert entries
    for entry in entries:
        target = f.object(entry.object_id)
        assert isinstance(target, Mob), entry
        assert entry.uid.matches(target.mob_id), entry


def test_tracks_resolve_to_components(f):
    for mob in f.mobs:
        for track in (mob.tracks or []):
            assert isinstance(track, Track)
            assert not isinstance(track.component, UnresolvedRef)


def test_sequences_contain_components(f):
    for sequence in (o for o in f.objects() if isinstance(o, Sequence)):
        for component in sequence:
            assert not isinstance(component, UnresolvedRef)


def test_source_clips_resolve_or_are_original(f):
    seen_any = False
    for mob in f.mobs:
        for clip in mob.source_clips():
            seen_any = True
            if clip.is_original:
                assert clip.source_mob() is None
            else:
                assert clip.source_mob() is not None, clip
    assert seen_any, "expected at least one source clip"


def test_derivation_chain_terminates(f):
    for mob in f.mobs:
        chain = mob.derivation_chain()
        assert chain[0] is mob
        assert len({m.object_id for m in chain}) == len(chain), "chain must not repeat"


def test_descriptors_and_locators(f):
    for mob in f.mobs:
        descriptor = mob.descriptor
        if descriptor is None:
            continue
        assert isinstance(descriptor, MediaDescriptor)
        assert isinstance(descriptor.summary(), str)
        for locator in descriptor.locators():
            assert isinstance(locator, Locator)


def test_duplicate_properties_are_all_preserved(f):
    """MobIDs are written twice; the reader must expose both and pick one."""
    duplicated = [m for m in f.mobs if len(m.values("OMFI:MOBJ:MobID")) > 1]
    assert duplicated, "the reference samples write MOBJ:MobID twice"
    for mob in duplicated:
        values = mob.values("OMFI:MOBJ:MobID")
        assert mob.mob_id == values[-1]
        assert len(set(v.bytes for v in values)) == 1, "duplicates are identical"


def test_attribute_kinds_match_their_value_property(f):
    """kind 1/2/3/4 -> int / string / object / bob."""
    expected = {1: "OMFI:ATTB:IntAttribute", 2: "OMFI:ATTB:StringAttribute",
                3: "OMFI:ATTB:ObjAttribute", 4: "OMFI:ATTB:BobData"}
    seen = set()
    for attr in (o for o in f.objects() if isinstance(o, Attribute)):
        prop = expected.get(attr.kind)
        assert prop is not None, "unknown attribute kind %r" % attr.kind
        assert prop in attr, attr
        assert attr.value is not None
        seen.add(attr.kind)
    assert seen, "expected attributes in every sample"


def test_attribute_names_are_strings(f):
    for attr in (o for o in f.objects() if isinstance(o, Attribute)):
        assert isinstance(attr.name, str) and attr.name


def test_attribute_trees_are_navigable(f):
    lists = [o for o in f.objects() if isinstance(o, AttributeList)]
    assert lists
    for attr_list in lists:
        flat = attr_list.to_attribute_dict(recursive=True)
        assert isinstance(flat, dict)


def test_class_dictionary_declares_extension_classes(f):
    entries = f.class_dictionary
    assert entries
    by_4cc = {c.class_4cc: c for c in entries}
    # Avid's own inheritance, identical in both reference samples
    assert by_4cc["CDCI"].parent_4cc == "DIDD"
    assert by_4cc["DIDD"].parent_4cc == "MDFL"
    assert by_4cc["MSML"].parent_4cc == "TXTL"
    # built-in OMF1 classes are assumed known and never declared
    assert "MOBJ" not in by_4cc and "TRAK" not in by_4cc


def test_msml_links_a_mob_to_a_volume(f):
    links = [o for o in f.by_class("MSML") if isinstance(o, MediaStreamLink)]
    if not links:
        pytest.skip("no MSML objects in this sample")
    for link in links:
        assert isinstance(link.mob_id, MobID)
        assert f.mob_by_id(link.mob_id) is not None, "MSML must name a real mob"
        assert link.volume


def test_unknown_class_still_reads_as_a_generic_object(f):
    """A class with no typed reader must degrade, not raise."""
    from mdb.core import CLASS_REGISTRY, MDBObject
    unknown = set(f.class_census()) - set(CLASS_REGISTRY)
    for class_id in unknown:
        for obj in f.by_class(class_id):
            assert isinstance(obj, MDBObject)
            assert obj.to_dict()


def test_attribute_error_names_the_property(f):
    with pytest.raises(AttributeError) as excinfo:
        f.header.definitely_not_a_property
    assert "definitely_not_a_property" in str(excinfo.value)


def test_missing_object_raises_key_error(f):
    assert f.object(0xDEADBEEF) is None
    with pytest.raises(KeyError):
        f[0xDEADBEEF]
