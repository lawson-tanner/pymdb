"""Value decoding, including the byte-level cases that are easy to get wrong."""
import datetime

import pytest

from mdb.datatypes import (MobIndexEntry, Opaque, Rational, SMPTELabel, decode)
from mdb.mobid import MobID, ShortUID


def test_integers_respect_signedness():
    assert decode("omfi:Long", bytes.fromhex("ffffffff")) == -1
    assert decode("omfi:Ulong", bytes.fromhex("ffffffff")) == 0xFFFFFFFF
    assert decode("omfi:Short", bytes.fromhex("ffff")) == -1
    assert decode("omfi:Ushort", bytes.fromhex("ffff")) == 0xFFFF


def test_string_stops_at_the_first_nul():
    assert decode("omfi:String", b"_PJ\0trailing garbage") == "_PJ"
    assert decode("omfi:String", b"\0") == ""


def test_object_tag_reads_in_order():
    assert decode("omfi:ObjectTag", b"WINL") == "WINL"


def test_byte_order_property_overrides_its_declared_type():
    """``OMFI:ByteOrder`` is typed omfi:Short but reads as ASCII."""
    assert decode("omfi:Short", b"II", property_name="OMFI:ByteOrder") == "II"
    assert decode("omfi:Short", b"II") == 0x4949


def test_exact_edit_rate():
    rate = decode("omfi:ExactEditRate", bytes.fromhex("1900000001000000"))
    assert rate == Rational(25, 1)
    assert float(rate) == 25.0
    assert str(rate) == "25/1"


def test_object_ref_array():
    raw = bytes.fromhex("0200" + "be09010000000000" + "c909010000000000")
    assert decode("omfi:ObjRefArray", raw) == [0x109BE, 0x109C9]


def test_object_ref_array_is_empty_when_count_is_zero():
    assert decode("omfi:ObjRefArray", bytes.fromhex("0000")) == []


def test_mob_index_reference_is_32_bit():
    """The trailing word is a separate field, not the top half of the ref.

    Reading the 20-byte record as UID + uint64 works only while that word is
    zero, which is true of SourceMobs and false of every CompositionMobs
    record.
    """
    raw = bytes.fromhex("0100" + "2a0000008b06671070080696" + "670a0100" + "58f99aeb")
    entries = decode("omfi:MobIndex", raw)
    assert len(entries) == 1
    assert entries[0].object_id == 0x10A67
    assert entries[0].extra == 0xEB9AF958
    assert entries[0].uid.prefix == 42


def test_uid_length_selects_the_representation():
    assert isinstance(decode("omfi:UID", b"\x01" * 32), MobID)
    assert isinstance(decode("omfi:UID", b"\x01" * 12), ShortUID)
    assert isinstance(decode("omfi:UID", b"\x01" * 7), Opaque)


def test_smpte_label_unswaps_the_aaf_auid_layout():
    """AAF stores a UL with its halves exchanged; canonical order is restored."""
    label = SMPTELabel(bytes.fromhex("01010104020100000 60e2b3404010101".replace(" ", "")))
    assert label.is_swapped_ul
    assert label.ul.hex() == "060e2b34040101010401010101020000"
    assert label.urn == "urn:smpte:ul:060e2b34.04010101.04010101.01020000"


def test_timestamp_zero_means_unset():
    assert decode("omfi:TimeStamp", b"\0" * 5) is None
    stamp = decode("omfi:TimeStamp", bytes.fromhex("b992746800000000"))
    assert isinstance(stamp, datetime.datetime)
    assert stamp.year == 2025


def test_unknown_type_degrades_to_opaque_rather_than_raising():
    value = decode("omfi:SomethingAvidAddedLastTuesday", b"\x01\x02\x03")
    assert isinstance(value, Opaque)
    assert value.raw == b"\x01\x02\x03"


def test_malformed_value_degrades_to_opaque():
    assert decode("omfi:GUID", b"\x01\x02") == Opaque("omfi:GUID", b"\x01\x02")


def test_short_uid_joins_to_a_mob_id():
    mob_id = MobID(bytes.fromhex(
        "060a2b34010101050101 0f10 13000000 950c671070080696 bdd3644ed768119f"
        .replace(" ", "")))
    assert mob_id.is_smpte_umid
    assert mob_id.short_uid.material == mob_id.material
    assert mob_id.short_uid.prefix == 42
    assert mob_id.short_uid.matches(mob_id)
    assert not ShortUID(b"\0" * 12).matches(mob_id)
    assert ShortUID(b"\0" * 12).is_null
