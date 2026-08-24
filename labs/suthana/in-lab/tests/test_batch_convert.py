#!/usr/bin/env python3
"""Tests for ``code/batch_convert.py``.

Discovery, output naming and runtimes lookup are covered as pure unit
tests. The batch run itself is exercised end-to-end on a mock incoming tree
built from the committed fixture (``tests/example_raw/``), mirroring the
layout of the incoming dandiset (one session folder holding the aligned
``.mat`` file and the shared runtimes CSV).

Test functions take their arguments positionally by pytest's injection
rules, so the repository's keyword-only and positional-only conventions do
not apply to them.

Run with::

    python3 -m pytest tests/ -q
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pynwb
import pytest

TESTS = Path(__file__).resolve().parent
CODE = TESTS.parent / "code"
sys.path.insert(0, str(CODE))

import batch_convert  # noqa: E402

sys.path.insert(0, str(TESTS))

import generate_fixtures  # noqa: E402

pytestmark = pytest.mark.ai_generated

EXAMPLE_RAW = TESTS / "example_raw"
EXAMPLE_MAT = EXAMPLE_RAW / generate_fixtures.MAT_FILENAME
EXAMPLE_RUNTIMES = EXAMPLE_RAW / generate_fixtures.RUNTIMES_FILENAME
CONFIG = TESTS / "config.yaml"

EXPECTED_NWB = Path("sub-S1") / "sub-S1_ses-inlab_behavior+ecephys.nwb"


@pytest.fixture
def sample_incoming(tmp_path):
    """A mock incoming dandiset holding one raw session folder."""
    session = tmp_path / "incoming" / "sourcedata" / "raw" / "sample-1"
    session.mkdir(parents=True)
    shutil.copy(EXAMPLE_MAT, session / generate_fixtures.MAT_FILENAME)
    shutil.copy(EXAMPLE_RUNTIMES, session / generate_fixtures.RUNTIMES_FILENAME)
    return tmp_path / "incoming"


def test_discover_subjects_finds_every_mat_file(tmp_path):
    incoming = tmp_path / "incoming"
    (incoming / "sample-1").mkdir(parents=True)
    (incoming / "sample-1" / "b.mat").touch()
    (incoming / "sample-2").mkdir()
    (incoming / "sample-2" / "a.mat").touch()
    (incoming / "sample-1" / "notes.txt").touch()

    discovered = batch_convert.discover_subjects(incoming)

    assert [path.name for path in discovered] == ["b.mat", "a.mat"]


def test_output_path_uses_the_dandi_subject_layout():
    nwb_path = batch_convert.output_path(standardized_dir=Path("/out"), paper_id="S3")

    assert nwb_path == Path("/out/sub-S3/sub-S3_ses-inlab_behavior+ecephys.nwb")


def test_find_runtimes_prefers_the_copy_beside_the_mat(tmp_path):
    incoming = tmp_path / "incoming"
    session = incoming / "sample-1"
    session.mkdir(parents=True)
    mat_path = session / "a.mat"
    mat_path.touch()
    beside = session / generate_fixtures.RUNTIMES_FILENAME
    beside.touch()
    (incoming / generate_fixtures.RUNTIMES_FILENAME).touch()

    found = batch_convert.find_runtimes(mat_path=mat_path, incoming_dir=incoming)

    assert found == beside


def test_find_runtimes_falls_back_to_the_incoming_tree(tmp_path):
    incoming = tmp_path / "incoming"
    session = incoming / "sample-1"
    session.mkdir(parents=True)
    mat_path = session / "a.mat"
    mat_path.touch()
    elsewhere = incoming / generate_fixtures.RUNTIMES_FILENAME
    elsewhere.touch()

    found = batch_convert.find_runtimes(mat_path=mat_path, incoming_dir=incoming)

    assert found == elsewhere


def test_find_runtimes_raises_when_none_exists(tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    mat_path = incoming / "a.mat"
    mat_path.touch()

    with pytest.raises(FileNotFoundError, match=generate_fixtures.RUNTIMES_FILENAME):
        batch_convert.find_runtimes(mat_path=mat_path, incoming_dir=incoming)


def test_paper_id_comes_from_the_file_not_the_filename(sample_incoming, tmp_path):
    """A renamed upload must still land under its own subject folder."""
    renamed = sample_incoming / "sourcedata" / "raw" / "sample-1" / "totally_unrelated_name.mat"
    (sample_incoming / "sourcedata" / "raw" / "sample-1" / generate_fixtures.MAT_FILENAME).rename(renamed)
    cfg = batch_convert.load_cfg(CONFIG)

    paper_id = batch_convert.paper_id_for(mat_path=renamed, cfg=cfg)

    assert paper_id == generate_fixtures.PAPER_ID


def test_convert_batch_end_to_end(sample_incoming, tmp_path):
    standardized = tmp_path / "standardized"

    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming,
        standardized_dir=standardized,
        config_path=CONFIG,
    )

    assert exit_code == 0
    out_nwb = standardized / EXPECTED_NWB
    assert out_nwb.is_file() is True
    with pynwb.NWBHDF5IO(out_nwb, "r") as io:
        nwbfile = io.read()
        assert nwbfile.subject.subject_id == generate_fixtures.PAPER_ID


def test_convert_batch_skips_existing_output(sample_incoming, tmp_path, capsys):
    standardized = tmp_path / "standardized"
    out_nwb = standardized / EXPECTED_NWB
    out_nwb.parent.mkdir(parents=True)
    out_nwb.write_text("not really an nwb file")

    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming,
        standardized_dir=standardized,
        config_path=CONFIG,
    )

    assert exit_code == 0
    assert out_nwb.read_text() == "not really an nwb file"
    assert "Exists, skipping" in capsys.readouterr().out


def test_convert_batch_overwrite_reconverts(sample_incoming, tmp_path):
    standardized = tmp_path / "standardized"
    out_nwb = standardized / EXPECTED_NWB
    out_nwb.parent.mkdir(parents=True)
    out_nwb.write_text("not really an nwb file")

    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming,
        standardized_dir=standardized,
        config_path=CONFIG,
        overwrite=True,
    )

    assert exit_code == 0
    with pynwb.NWBHDF5IO(out_nwb, "r") as io:
        assert io.read().subject.subject_id == generate_fixtures.PAPER_ID


def test_convert_batch_reports_an_unknown_subject(sample_incoming, tmp_path, capsys):
    """A .mat naming a subject the config doesn't describe fails that file only."""
    stray = sample_incoming / "sourcedata" / "raw" / "sample-2"
    stray.mkdir(parents=True)
    (stray / "broken.mat").write_text("not an hdf5 file")

    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming,
        standardized_dir=tmp_path / "standardized",
        config_path=CONFIG,
    )

    assert exit_code == 1
    assert "FAILED" in capsys.readouterr().err
    assert (tmp_path / "standardized" / EXPECTED_NWB).is_file() is True


def test_convert_batch_empty_input(tmp_path, capsys):
    incoming = tmp_path / "incoming"
    incoming.mkdir()

    exit_code = batch_convert.convert_batch(
        incoming_dir=incoming,
        standardized_dir=tmp_path / "standardized",
        config_path=CONFIG,
    )

    assert exit_code == 0
    assert "No .mat files found" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("requested", "task_count", "expected_workers"),
    [(None, 1, 1), (4, 2, 2), (2, 8, 2), (0, 5, 1)],
)
def test_resolve_worker_count(requested, task_count, expected_workers):
    worker_count = batch_convert.resolve_worker_count(requested=requested, task_count=task_count)

    assert worker_count == expected_workers
