#!/usr/bin/env python3
"""Tests for the pure helpers in ``code/_sanes_to_nwb.py``.

``build_nwb`` itself still needs real audio, video, SLEAP and annotation
fixtures this repository does not have yet (see ``labs/sanes/README.md``), so
what is covered here is the file-discovery logic that runs before any of that
and decides which files a chunk contributes.

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


@pytest.mark.parametrize("filename", ["annotations.csv", "channel_0_4_annotations.csv"])
def test_find_annotations_file_accepts_either_naming(tmp_path, filename):
    """Both namings appear across the chunks of one real upload (000522)."""
    (tmp_path / filename).touch()

    annotations_path = _sanes_to_nwb.find_annotations_file(tmp_path)

    assert annotations_path == tmp_path / filename


def test_find_annotations_file_ignores_the_tracks_csv(tmp_path):
    """Every chunk also holds a SLEAP tracks .csv, which is not the annotations table."""
    (tmp_path / "center-session_135_video-4.tracks.csv").touch()
    (tmp_path / "channel_0_4_annotations.csv").touch()

    annotations_path = _sanes_to_nwb.find_annotations_file(tmp_path)

    assert annotations_path == tmp_path / "channel_0_4_annotations.csv"


@pytest.mark.parametrize(
    ("filenames", "expected_found"),
    [
        ((), 0),
        (("center-session_135_video-4.tracks.csv",), 0),
        (("annotations.csv", "channel_0_4_annotations.csv"), 2),
    ],
)
def test_find_annotations_file_requires_exactly_one(tmp_path, filenames, expected_found):
    for filename in filenames:
        (tmp_path / filename).touch()

    with pytest.raises(ValueError, match=f"found {expected_found}"):
        _sanes_to_nwb.find_annotations_file(tmp_path)
