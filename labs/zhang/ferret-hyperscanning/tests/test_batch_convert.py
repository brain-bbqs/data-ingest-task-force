#!/usr/bin/env python3
"""Unit tests for the identity rules and the batch driver's own logic.

Discovery, output paths, the skip/overwrite bookkeeping and the empty-input
case are exercised with ``convert_session`` stubbed out, so they run in
milliseconds and need no NWB stack beyond the imports.

Run with::

    python3 -m pytest tests/ -q
"""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent
sys.path.insert(0, str(PROJECT / "code"))

import _zhang_ferret_hyperscanning_to_nwb as core  # noqa: E402
import batch_convert  # noqa: E402

pytestmark = pytest.mark.ai_generated

REC_STEM = "0236HS3_0237HS4_20260401_130419"


def make_rec_dir(root, /, *, pair="0236-0237", date_dirname="04.01.2026", stem=REC_STEM):
    rec_dir = root / batch_convert.RAW_SUBTREE / pair / date_dirname / f"{stem}.rec"
    rec_dir.mkdir(parents=True)
    (rec_dir / f"{stem}.rec").write_bytes(b"<Configuration></Configuration>\n")
    return rec_dir


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        (REC_STEM, "20260401T130419"),
        ("0235HS1_0236HS2_20260306_154100", "20260306T154100"),
    ],
)
def test_derive_session_label(stem, expected):
    assert core.derive_session_label(stem) == expected


def test_derive_subject_labels_keeps_basename_order():
    headstages = core.derive_subject_labels(REC_STEM)
    assert [(h.subject, h.headstage, h.position) for h in headstages] == [("0236", "3", 0), ("0237", "4", 1)]


@pytest.mark.parametrize("stem", ["notes", "0236_0237_20260401", "0236HS3-0237HS4_20260401_130419"])
def test_unrecognized_names_are_errors(stem):
    with pytest.raises(ValueError):
        core.derive_session_label(stem)


def test_parse_rec_identity(tmp_path):
    rec_dir = make_rec_dir(tmp_path)
    identity = core.parse_rec_identity(rec_dir)
    assert identity.rec_path == rec_dir / f"{REC_STEM}.rec"
    assert identity.pair == "0236-0237"
    assert identity.host_subject == "0236"
    assert identity.name_start == datetime.datetime(2026, 4, 1, 13, 4, 19)


def test_parse_rec_identity_rejects_pair_mismatch(tmp_path):
    rec_dir = make_rec_dir(tmp_path, pair="0235-0237")
    with pytest.raises(ValueError, match="sits under"):
        core.parse_rec_identity(rec_dir)


def test_output_paths_follow_dandi_layout(tmp_path):
    identity = core.parse_rec_identity(make_rec_dir(tmp_path))
    paths = core.output_paths(output_dir=tmp_path / "out", identity=identity)
    assert paths == {
        "0236": tmp_path / "out" / "sub-0236" / "sub-0236_ses-20260401T130419_behavior+ecephys.nwb",
        "0237": tmp_path / "out" / "sub-0237" / "sub-0237_ses-20260401T130419_behavior+ecephys.nwb",
    }
    destination = core.video_destination(output_dir=tmp_path / "out", identity=identity, camera=14, kind="video")
    assert destination == tmp_path / "out" / "sub-0236" / "sub-0236_ses-20260401T130419_cam14_video.avi"


def test_match_videos_picks_nearest_stamp_per_camera(tmp_path):
    rec_dir = make_rec_dir(tmp_path)
    videos = rec_dir.parent / "Videos"
    videos.mkdir()
    for name in [
        "cam14-04012026122439-0000.avi",
        "cam14-04012026162439-0000.avi",
        "cam14-cal-04012026121856-0000.avi",
        "cam46-04012026122433-0000.avi",
        "README.txt",
    ]:
        (videos / name).write_bytes(b"")
    matched, unmatched = core.match_videos(rec_dir)
    assert matched[14]["video"].name == "cam14-04012026122439-0000.avi"
    assert matched[14]["calibration"].name == "cam14-cal-04012026121856-0000.avi"
    assert matched[46] == {"video": videos / "cam46-04012026122433-0000.avi"}
    assert [path.name for path in unmatched] == ["README.txt"]


def test_match_videos_without_videos_dir(tmp_path):
    matched, unmatched = core.match_videos(make_rec_dir(tmp_path))
    assert (matched, unmatched) == ({}, [])


@pytest.mark.parametrize(
    ("start", "expected_start"),
    [
        (datetime.datetime(2026, 3, 27, 13, 8, 0), "13:05"),
        (datetime.datetime(2026, 3, 27, 13, 30, 0), "13:33"),
    ],
)
def test_find_session_row_nearest_start(start, expected_start):
    rows = [
        {"date": "2026-03-27", "pair": "0235-0236", "start": "13:05", "belly_up": "0"},
        {"date": "2026-03-27", "pair": "0235-0236", "start": "13:33", "belly_up": "0"},
        {"date": "2026-03-27", "pair": "0236-0237", "start": "14:37", "belly_up": "1"},
    ]
    row = core.find_session_row(rows, pair="0235-0236", start=start)
    assert row["start"] == expected_start


def test_find_session_row_missing():
    rows = [{"date": "2026-03-27", "pair": "0235-0236", "start": "13:05", "belly_up": "0"}]
    assert core.find_session_row(rows, pair="0236-0237", start=datetime.datetime(2026, 3, 27, 14, 0)) is None


@pytest.mark.parametrize(
    ("belly_up", "channel", "expected_region"),
    [(False, 1, "PMC"), (False, 0, "PPC"), (True, 1, "PPC"), (True, 0, "PMC")],
)
def test_select_channel_map(belly_up, channel, expected_region):
    cfg = core.load_cfg(PROJECT / "code" / "config.yaml")
    channel_map = core.select_channel_map(belly_up=belly_up, cfg=cfg)
    assert channel_map["odd" if channel % 2 else "even"] == expected_region


@pytest.mark.parametrize(("position", "expected"), [(0, ["0", "1"]), (1, ["32", "33"])])
def test_headstage_channel_ids(position, expected):
    selected = core.headstage_channel_ids(
        channel_ids=["0", "32", "1", "33"], position=position, channels_per_headstage=32
    )
    assert selected == expected


def test_discover_recordings_reports_strays(tmp_path):
    first = make_rec_dir(tmp_path)
    second = make_rec_dir(tmp_path, pair="0235-0237", stem="0235HS1_0237HS4_20260401_150800")
    (first.parent / "Videos").mkdir()
    (first.parent / "scratch").mkdir()
    (first.parent / "notes.txt").write_text("stray\n")
    recordings, ignored = batch_convert.discover_recordings(tmp_path)
    assert recordings == [second, first]
    assert [path.name for path in ignored] == ["notes.txt", "scratch"]


def test_empty_incoming_exits_zero(tmp_path, capsys):
    exit_code = batch_convert.convert_batch(
        incoming_dir=tmp_path, standardized_dir=tmp_path / "out", config_path=PROJECT / "code" / "config.yaml"
    )
    assert exit_code == 0
    assert "No .rec recordings found" in capsys.readouterr().out


def test_skip_and_overwrite_bookkeeping(tmp_path, monkeypatch, capsys):
    rec_dir = make_rec_dir(tmp_path)
    identity = core.parse_rec_identity(rec_dir)
    out_dir = tmp_path / "out"
    for path in core.output_paths(output_dir=out_dir, identity=identity).values():
        path.parent.mkdir(parents=True)
        path.write_bytes(b"")
    calls = []

    def fake_convert(*, rec, output_dir, cfg, session_log=None, overwrite=False):
        calls.append((Path(rec), overwrite))
        return list(core.output_paths(output_dir=output_dir, identity=core.parse_rec_identity(rec)).values())

    monkeypatch.setattr(core, "convert_session", fake_convert)
    monkeypatch.setattr(batch_convert, "convert_session", fake_convert)
    config_path = PROJECT / "code" / "config.yaml"

    assert batch_convert.convert_batch(incoming_dir=tmp_path, standardized_dir=out_dir, config_path=config_path) == 0
    assert calls == []
    assert "Exists, skipping" in capsys.readouterr().out

    exit_code = batch_convert.convert_batch(
        incoming_dir=tmp_path, standardized_dir=out_dir, config_path=config_path, overwrite=True, max_workers=1
    )
    assert exit_code == 0
    assert "Converted 1, skipped 0, failed 0 of 1" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("requested", "task_count", "expected"),
    [(None, 1, 1), (None, 10, min(batch_convert.DEFAULT_JOBS, os.cpu_count() or 1)), (8, 3, 3), (1, 5, 1)],
)
def test_resolve_worker_count(requested, task_count, expected):
    assert batch_convert.resolve_worker_count(requested=requested, task_count=task_count) == expected


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
