#!/usr/bin/env python3
"""Tests for the pure helpers in ``code/_sanes_to_nwb.py``.

``build_nwb`` itself needs real audio, video, SLEAP and annotation fixtures
this repository does not have yet (see ``labs/sanes/README.md``), so what is
covered here is the file-discovery and offset-bookkeeping logic that runs
before any of that.

Test functions take their arguments positionally by pytest's injection rules,
so the repository's keyword-only and positional-only conventions do not apply
to them.

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

from labs.sanes.code import _sanes_to_nwb  # noqa: E402

pytestmark = pytest.mark.ai_generated


def test_discover_chunk_folders_natural_sorts_and_ignores_other_folders(tmp_path):
    for name in ("idx_10", "idx_2", "idx_1", "not_a_chunk"):
        (tmp_path / name).mkdir()
    (tmp_path / "idx_1_readme.txt").touch()  # a file, not a folder -- must not match

    folders = _sanes_to_nwb.discover_chunk_folders(tmp_path)

    assert [folder.name for folder in folders] == ["idx_1", "idx_2", "idx_10"]


def test_chunk_video_path_finds_the_one_mp4(tmp_path):
    (tmp_path / "notes.txt").touch()
    (tmp_path / "center-session_video-0.mp4").touch()

    video = _sanes_to_nwb.chunk_video_path(tmp_path)

    assert video == tmp_path / "center-session_video-0.mp4"


@pytest.mark.parametrize(
    ("configured", "expected_is_none"),
    [
        ("", True),
        ("2025-10-1310:35:00+0000", False),
    ],
)
def test_session_start_time(configured, expected_is_none):
    """An empty config falls back to the time of conversion, matching the v2
    scripts; a configured value is parsed against their fixed format."""
    cfg = {"session": {"start_time": configured}}

    start_time = _sanes_to_nwb.session_start_time(cfg)

    assert (start_time is None) is False
    if not expected_is_none:
        assert start_time.isoformat() == "2025-10-13T10:35:00+00:00"


def test_read_chunk_annotations_offsets_start_and_stop(tmp_path):
    (tmp_path / "annotations.csv").write_text("start_seconds,stop_seconds,name\n0.1,0.2,call_a\n0.5,0.6,call_b\n")

    df = _sanes_to_nwb.read_chunk_annotations(tmp_path, cumulative_offset=10.0)

    assert list(df["start_seconds"]) == [10.1, 10.5]
    assert list(df["stop_seconds"]) == [10.2, 10.6]


def test_merge_chunk_sleap_labels_requires_at_least_one_slp(tmp_path):
    chunk = tmp_path / "idx_0"
    chunk.mkdir()

    with pytest.raises(ValueError, match="No .slp files found"):
        _sanes_to_nwb.merge_chunk_sleap_labels([chunk])
