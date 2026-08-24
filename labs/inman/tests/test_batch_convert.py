#!/usr/bin/env python3
"""Tests for ``code/batch_convert.py``.

Discovery and identity parsing are covered as pure unit tests. The batch
run itself is exercised end-to-end on a mock incoming tree built from the
committed fixture (``tests/example_raw/``), mirroring the current layout of
the incoming dandiset (one session folder, e.g. ``sample-1/``, holding one
``.mat`` file). Copies of that fixture under several folder names stand in
for the multi-walk trees the parallel conversion needs.

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
REPO_ROOT = TESTS.parents[2]
sys.path.insert(0, str(REPO_ROOT))

from labs.inman.code import batch_convert  # noqa: E402

pytestmark = pytest.mark.ai_generated

EXAMPLE_MAT = TESTS / "example_raw" / "RWNApp_RW3_Walk1_restructured.mat"
CONFIG = TESTS / "config.yaml"


@pytest.mark.parametrize(
    ("filename", "expected_identity"),
    [
        ("RWNApp_RW3_Walk1_restructured.mat", ("3", 1)),
        ("RWNApp_RW12_Walk7_restructured.mat", ("12", 7)),
        ("rwnapp_rw4_walk2.mat", ("4", 2)),
        ("some_other_recording.mat", None),
    ],
)
def test_parse_walk_identity(filename, expected_identity):
    identity = batch_convert.parse_walk_identity(Path(filename))
    assert identity == expected_identity


def test_discover_walks_with_fallback(tmp_path):
    incoming = tmp_path / "incoming"
    (incoming / "sample-1").mkdir(parents=True)
    (incoming / "sample-1" / "RWNApp_RW3_Walk1_restructured.mat").touch()
    (incoming / "sample-2").mkdir()
    (incoming / "sample-2" / "unnamed_a.mat").touch()
    (incoming / "sample-2" / "unnamed_b.mat").touch()
    (incoming / "sample-1" / "notes.txt").touch()

    walks = batch_convert.discover_walks(incoming)
    identities = [(mat_path.name, subject, walk) for mat_path, subject, walk in walks]
    assert identities == [
        ("RWNApp_RW3_Walk1_restructured.mat", "3", 1),
        ("unnamed_a.mat", "sample2", 1),
        ("unnamed_b.mat", "sample2", 2),
    ]


def test_output_path():
    nwb_path = batch_convert.output_path(standardized_dir=Path("out"), subject="3", walk=1)
    assert nwb_path == Path("out/sub-3/sub-3_ses-walk1_behavior+ecephys.nwb")


@pytest.fixture()
def sample_incoming(tmp_path):
    incoming = tmp_path / "incoming"
    session_dir = incoming / "sample-1"
    session_dir.mkdir(parents=True)
    shutil.copy2(EXAMPLE_MAT, session_dir / EXAMPLE_MAT.name)
    return incoming


def test_convert_batch_end_to_end(sample_incoming, tmp_path):
    standardized = tmp_path / "standardized"
    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming, standardized_dir=standardized, config_path=CONFIG
    )
    assert exit_code == 0

    out_nwb = standardized / "sub-3" / "sub-3_ses-walk1_behavior+ecephys.nwb"
    assert out_nwb.is_file()
    with pynwb.NWBHDF5IO(out_nwb, "r") as io:
        nwbfile = io.read()
        assert nwbfile.identifier == "InmanWalk-Subject3-Walk1"

    # A rerun without --overwrite must leave the existing output untouched.
    first_mtime = out_nwb.stat().st_mtime_ns
    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming, standardized_dir=standardized, config_path=CONFIG
    )
    assert exit_code == 0
    assert out_nwb.stat().st_mtime_ns == first_mtime

    # With overwrite=True the walk is reconverted.
    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming, standardized_dir=standardized, config_path=CONFIG, overwrite=True
    )
    assert exit_code == 0
    assert out_nwb.stat().st_mtime_ns > first_mtime


def test_convert_batch_continues_past_failures(sample_incoming, tmp_path, capsys):
    bad_dir = sample_incoming / "sample-2"
    bad_dir.mkdir()
    (bad_dir / "RWNApp_RW9_Walk9_restructured.mat").write_bytes(b"not a mat file")

    standardized = tmp_path / "standardized"
    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming, standardized_dir=standardized, config_path=CONFIG
    )
    assert exit_code == 1

    good_output = standardized / "sub-3" / "sub-3_ses-walk1_behavior+ecephys.nwb"
    assert good_output.is_file()
    captured = capsys.readouterr()
    assert "FAILED" in captured.err


def test_convert_batch_removes_legacy_nested_output(sample_incoming, tmp_path):
    standardized = tmp_path / "standardized"
    legacy_dir = standardized / "sub-3" / "ses-walk1"
    legacy_dir.mkdir(parents=True)
    legacy_nwb = legacy_dir / "sub-3_ses-walk1_behavior+ecephys.nwb"
    legacy_nwb.write_bytes(b"stale output from the nested layout")

    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming, standardized_dir=standardized, config_path=CONFIG
    )
    assert exit_code == 0
    assert not legacy_nwb.exists()
    assert not legacy_dir.exists()
    assert (standardized / "sub-3" / "sub-3_ses-walk1_behavior+ecephys.nwb").is_file()


@pytest.mark.parametrize(
    ("requested", "task_count", "expected_workers"),
    [
        (None, 1, 1),
        (4, 2, 2),
        (2, 8, 2),
        (0, 8, 1),
        (-1, 8, 1),
    ],
)
def test_resolve_worker_count(requested, task_count, expected_workers):
    worker_count = batch_convert.resolve_worker_count(requested=requested, task_count=task_count)
    assert worker_count == expected_workers


def test_convert_batch_parallel_over_walks(tmp_path):
    incoming = tmp_path / "incoming"
    walks = [(3, 1), (3, 2), (4, 1)]
    for subject, walk in walks:
        session_dir = incoming / f"sample-{subject}-{walk}"
        session_dir.mkdir(parents=True)
        shutil.copy2(EXAMPLE_MAT, session_dir / f"RWNApp_RW{subject}_Walk{walk}_restructured.mat")

    standardized = tmp_path / "standardized"
    exit_code = batch_convert.convert_batch(
        incoming_dir=incoming, standardized_dir=standardized, config_path=CONFIG, max_workers=3
    )
    assert exit_code == 0

    for subject, walk in walks:
        out_nwb = batch_convert.output_path(standardized_dir=standardized, subject=str(subject), walk=walk)
        assert out_nwb.is_file()
        with pynwb.NWBHDF5IO(out_nwb, "r") as io:
            assert io.read().identifier == f"InmanWalk-Subject{subject}-Walk{walk}"


def test_convert_batch_parallel_reports_a_failed_walk(sample_incoming, tmp_path, capsys):
    bad_dir = sample_incoming / "sample-2"
    bad_dir.mkdir()
    (bad_dir / "RWNApp_RW9_Walk9_restructured.mat").write_bytes(b"not a mat file")

    standardized = tmp_path / "standardized"
    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming, standardized_dir=standardized, config_path=CONFIG, max_workers=2
    )
    assert exit_code == 1

    # The healthy walk still converts: one worker's failure does not cancel it.
    assert (standardized / "sub-3" / "sub-3_ses-walk1_behavior+ecephys.nwb").is_file()
    captured = capsys.readouterr()
    assert "FAILED" in captured.err


def test_convert_batch_empty_input(tmp_path, capsys):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    exit_code = batch_convert.convert_batch(
        incoming_dir=incoming, standardized_dir=tmp_path / "standardized", config_path=CONFIG
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No .mat files found" in captured.out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
