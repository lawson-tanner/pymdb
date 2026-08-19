"""The command line -- exercised end to end, since that is how it is used."""
import pytest

from mdb.cli import main


def _run(capsys, *argv):
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_summary(capsys, sample_path):
    code, out, _ = _run(capsys, "summary", str(sample_path))
    assert code == 0
    assert "container       Bento 1.0" in out
    assert "MOBJ" in out


def test_mobs(capsys, sample_path):
    code, out, _ = _run(capsys, "mobs", str(sample_path))
    assert code == 0
    assert "mob(s)" in out


def test_paths(capsys, sample_path):
    code, out, _ = _run(capsys, "paths", str(sample_path))
    assert code == 0


def test_classes(capsys, sample_path):
    code, out, _ = _run(capsys, "classes", str(sample_path))
    assert code == 0
    assert "CDCI" in out


def test_obj_dumps_the_first_data_object(capsys, sample_path):
    code, out, _ = _run(capsys, "obj", str(sample_path), "0x109a0")
    assert code == 0
    assert "OMFI:ObjID" in out


def test_obj_reports_a_missing_object(capsys, sample_path):
    code, _, err = _run(capsys, "obj", str(sample_path), "0xdeadbeef")
    assert code == 2
    assert "no object" in err


def test_tree(capsys, sample_path):
    code, out, _ = _run(capsys, "tree", str(sample_path), "--depth", "4")
    assert code == 0
    assert "MOBJ" in out


def test_owner(capsys, sample_path):
    code, out, _ = _run(capsys, "owner", str(sample_path), "0x0")
    assert code == 0
    assert "obj 0x" in out


def test_find_reports_a_miss(capsys, sample_path):
    code, _, err = _run(capsys, "find", str(sample_path), "zzz-not-in-any-mdb-zzz")
    assert code == 1
    assert "no match" in err


def test_validate_exits_zero_on_a_healthy_file(capsys, sample_path):
    code, out, _ = _run(capsys, "validate", str(sample_path))
    assert code == 0
    assert "0 error(s)" in out


def test_unreadable_file_is_reported(capsys, tmp_path):
    junk = tmp_path / "junk.mdb"
    junk.write_bytes(b"not an mdb at all" * 10)
    code, _, err = _run(capsys, "summary", str(junk))
    assert code == 2
    assert "NotABentoContainer" in err


def test_no_command_prints_help(capsys):
    code, out, _ = _run(capsys)
    assert code == 2
    assert "COMMAND" in out
