#!/usr/bin/env python3
"""Tests for the parallel session conversion in ``code/convert_raw_to_bids.py``.

The committed fixture holds a single session, so the multi-session tree these
tests need is built by copying it under several raw folder names. The point is
that spreading sessions across workers changes only how fast the run is, never
what it writes.

Run with::

    python3 -m pytest tests/ -q
"""

from __future__ import annotations

import shutil
import stat
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
sys.path.insert(0, str(REPO / "code"))

import convert_raw_to_bids as conv  # noqa: E402

pytestmark = pytest.mark.ai_generated

EXAMPLE_RAW = TESTS / "example_raw"
FIXTURE_SESSION = EXAMPLE_RAW / "07102026-Session1"
SHIM = TESTS / "ffprobe_shim.py"


def _build_raw_tree(root: Path, folder_names: list[str]) -> Path:
    raw = root / "raw"
    for name in folder_names:
        shutil.copytree(FIXTURE_SESSION, raw / name)
    return raw


def _convert(raw_dir: Path, bids_dir: Path, jobs: int | None) -> conv.Converter:
    SHIM.chmod(SHIM.stat().st_mode | stat.S_IEXEC | stat.S_IRUSR)
    converter = conv.Converter(
        raw_dir=raw_dir,
        bids_dir=bids_dir,
        ffprobe_bin=str(SHIM),
        species="Ovis aries",
        authors=["Kemere Lab"],
        max_workers=jobs,
    )
    assert converter.run() == 0
    return converter


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


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
    worker_count = conv.resolve_worker_count(requested=requested, task_count=task_count)
    assert worker_count == expected_workers


def test_session_groups_bucket_colliding_labels(tmp_path):
    raw = _build_raw_tree(tmp_path, ["07102026-Session1", "07102026_Session_1", "07112026-Session1"])
    converter = conv.Converter(raw_dir=raw, bids_dir=tmp_path / "bids")

    groups = converter.session_groups()
    grouped_names = sorted(sorted(p.name for p in group) for group in groups)
    assert grouped_names == [["07102026-Session1", "07102026_Session_1"], ["07112026-Session1"]]


def test_parallel_matches_sequential(tmp_path):
    folder_names = ["07102026-Session1", "07112026-Session1", "07122026-Session1", "07132026-Session1"]
    raw = _build_raw_tree(tmp_path, folder_names)

    sequential = _convert(raw, tmp_path / "sequential", 1)
    parallel = _convert(raw, tmp_path / "parallel", 4)

    assert _tree(tmp_path / "parallel") == _tree(tmp_path / "sequential")
    assert parallel.converted == sequential.converted
    assert sorted(parallel.warnings) == sorted(sequential.warnings)
    assert sorted(parallel.skipped_files) == sorted(sequential.skipped_files)
    assert sorted(parallel.scans) == [f"2026071{day}" for day in range(4)]


def test_colliding_labels_convert_deterministically(tmp_path):
    raw = _build_raw_tree(tmp_path, ["07102026-Session1", "07102026_Session_1"])

    sequential = _convert(raw, tmp_path / "sequential", 1)
    parallel = _convert(raw, tmp_path / "parallel", 4)

    assert _tree(tmp_path / "parallel") == _tree(tmp_path / "sequential")
    # Both raw folders land in ses-20260710, so the second one's media is
    # disambiguated with an acq entity rather than overwriting the first.
    session_files = sorted(
        p.name for p in (tmp_path / "parallel" / "sub-multi" / "ses-20260710" / "beh").iterdir() if p.suffix == ".mp4"
    )
    assert len(session_files) == 2
    assert parallel.converted == sequential.converted


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
