"""Test fixtures.

The suite runs against real Media Composer output.  Point ``PYMDB_SAMPLES`` at
a directory of ``.mdb`` files, or drop them in ``tests/samples/``; tests that
need a sample skip cleanly when none is present, so the structural tests still
run in a bare checkout.
"""
import os
import pathlib

import pytest

import mdb

HERE = pathlib.Path(__file__).parent
SAMPLE_DIRS = [
    pathlib.Path(os.environ["PYMDB_SAMPLES"]) if os.environ.get("PYMDB_SAMPLES") else None,
    HERE / "samples",
    HERE.parent / "samples",
    HERE.parent.parent / "samples",
]


def _find_samples():
    for directory in SAMPLE_DIRS:
        if directory and directory.is_dir():
            found = sorted(directory.glob("*.mdb"))
            if found:
                return found
    return []


SAMPLES = _find_samples()

#: the two files every documented claim was verified against
REFERENCE_NAMES = ("msmMMOB_ImportedMedia.mdb", "msmMMOB_TranscodedMedia.mdb")


def _by_name(name):
    return next((p for p in SAMPLES if p.name == name), None)


def pytest_generate_tests(metafunc):
    if "sample_path" in metafunc.fixturenames:
        if SAMPLES:
            metafunc.parametrize("sample_path", SAMPLES, ids=[p.name for p in SAMPLES])
        else:
            metafunc.parametrize("sample_path", [
                pytest.param(None, marks=pytest.mark.skip(
                    reason="no .mdb samples found; set PYMDB_SAMPLES"))])


@pytest.fixture
def f(sample_path):
    """An open :class:`mdb.MDBFile` for each discovered sample."""
    with mdb.open(str(sample_path)) as handle:
        yield handle


@pytest.fixture
def imported():
    path = _by_name("msmMMOB_ImportedMedia.mdb")
    if path is None:
        pytest.skip("msmMMOB_ImportedMedia.mdb not available")
    with mdb.open(str(path)) as handle:
        yield handle


@pytest.fixture
def transcoded():
    path = _by_name("msmMMOB_TranscodedMedia.mdb")
    if path is None:
        pytest.skip("msmMMOB_TranscodedMedia.mdb not available")
    with mdb.open(str(path)) as handle:
        yield handle
