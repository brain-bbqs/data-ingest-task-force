#!/usr/bin/env python3
"""Tests for ``code/batch_convert.py``.

``shepherd_to_nwb.build_nwb`` needs real video/DeepLabCut fixtures this repo
doesn't have yet (see ``labs/shepherd/README.md``), so these tests cover the
batch driver's own logic -- discovery, identity, output paths, and the
skip/overwrite bookkeeping -- with ``build_nwb`` stubbed out rather than
exercised for real. A real end-to-end integration test belongs with the
follow-up that fixes the ported converter.

Run with::

    python3 -m pytest tests/ -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
REPO_ROOT = TESTS.parents[2]
sys.path.insert(0, str(REPO_ROOT))

from labs.shepherd.code import batch_convert  # noqa: E402

pytestmark = pytest.mark.ai_generated

CONFIG = TESTS.parent / "code" / "config.yaml"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("sample-1", "sample1"),
        ("2025-06-25", "20250625"),
        ("!!!", "unknown"),
    ],
)
def test_sanitize_label(text, expected):
    label = batch_convert.sanitize_label(text) or "unknown"
    assert label == expected


def test_discover_sessions(tmp_path):
    raw_dir = tmp_path / "incoming" / "sourcedata" / "raw"
    (raw_dir / "sample-1").mkdir(parents=True)
    (raw_dir / "sample-2").mkdir()
    (raw_dir / "notes.txt").write_text("not a session")

    sessions = batch_convert.discover_sessions(tmp_path / "incoming")
    identities = [(session_dir.name, subject) for session_dir, subject in sessions]
    assert identities == [("sample-1", "sample1"), ("sample-2", "sample2")]


def test_discover_sessions_missing_raw_dir(tmp_path):
    assert batch_convert.discover_sessions(tmp_path / "incoming") == []


def test_output_stem():
    stem = batch_convert.output_stem(standardized_dir=Path("out"), subject="sample1", session="1")
    assert stem == Path("out/sub-sample1/sub-sample1_ses-1")


def test_is_complete_requires_both_files(tmp_path):
    stem = tmp_path / "sub-sample1_ses-1"
    assert batch_convert.is_complete(stem) is False

    Path(f"{stem}_desc-raw.nwb").touch()
    assert batch_convert.is_complete(stem) is False, "one of two files must not count as complete"

    Path(f"{stem}_desc-processed.nwb").touch()
    assert batch_convert.is_complete(stem) is True


@pytest.fixture()
def sample_incoming(tmp_path):
    incoming = tmp_path / "incoming"
    (incoming / "sourcedata" / "raw" / "sample-1").mkdir(parents=True)
    return incoming


def fake_build_nwb(*, input_file, subject_name, out_nwb, cfg):
    Path(f"{out_nwb}_desc-raw.nwb").write_text(input_file)
    Path(f"{out_nwb}_desc-processed.nwb").write_text(subject_name)


def test_convert_batch_end_to_end(sample_incoming, tmp_path, monkeypatch):
    monkeypatch.setattr(batch_convert, "build_nwb", fake_build_nwb)
    standardized = tmp_path / "standardized"

    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming, standardized_dir=standardized, config_path=CONFIG
    )
    assert exit_code == 0

    raw_nwb = standardized / "sub-sample1" / "sub-sample1_ses-1_desc-raw.nwb"
    processed_nwb = standardized / "sub-sample1" / "sub-sample1_ses-1_desc-processed.nwb"
    assert raw_nwb.is_file()
    assert processed_nwb.is_file()

    # A rerun without --overwrite must leave the existing outputs untouched.
    first_mtime = raw_nwb.stat().st_mtime_ns
    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming, standardized_dir=standardized, config_path=CONFIG
    )
    assert exit_code == 0
    assert raw_nwb.stat().st_mtime_ns == first_mtime

    # With overwrite=True the session is reconverted.
    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming, standardized_dir=standardized, config_path=CONFIG, overwrite=True
    )
    assert exit_code == 0
    assert raw_nwb.stat().st_mtime_ns > first_mtime


def test_convert_batch_reconverts_incomplete_pair(sample_incoming, tmp_path, monkeypatch):
    """A half-written pair from an interrupted run is redone even without --overwrite."""
    monkeypatch.setattr(batch_convert, "build_nwb", fake_build_nwb)
    standardized = tmp_path / "standardized"
    raw_nwb = standardized / "sub-sample1" / "sub-sample1_ses-1_desc-raw.nwb"
    raw_nwb.parent.mkdir(parents=True)
    raw_nwb.write_text("stale, from an interrupted run")

    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming, standardized_dir=standardized, config_path=CONFIG
    )
    assert exit_code == 0
    processed_nwb = standardized / "sub-sample1" / "sub-sample1_ses-1_desc-processed.nwb"
    assert processed_nwb.is_file()


def test_convert_batch_continues_past_failures(sample_incoming, tmp_path, monkeypatch, capsys):
    (sample_incoming / "sourcedata" / "raw" / "sample-2").mkdir()

    def flaky_build_nwb(*, input_file, subject_name, out_nwb, cfg):
        if "sample1" in subject_name:
            raise ValueError("boom")
        fake_build_nwb(input_file=input_file, subject_name=subject_name, out_nwb=out_nwb, cfg=cfg)

    monkeypatch.setattr(batch_convert, "build_nwb", flaky_build_nwb)
    standardized = tmp_path / "standardized"

    exit_code = batch_convert.convert_batch(
        incoming_dir=sample_incoming, standardized_dir=standardized, config_path=CONFIG
    )
    assert exit_code == 1, "a failed session must be reflected in the exit code"

    good_output = standardized / "sub-sample2" / "sub-sample2_ses-1_desc-raw.nwb"
    assert good_output.is_file(), "the failure of one session must not stop the others"

    captured = capsys.readouterr()
    assert "FAILED" in captured.err


def test_convert_batch_no_sessions(tmp_path, capsys):
    exit_code = batch_convert.convert_batch(
        incoming_dir=tmp_path / "empty", standardized_dir=tmp_path / "standardized", config_path=CONFIG
    )
    assert exit_code == 0
    assert "No session folders found" in capsys.readouterr().out
