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
import json
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
CONFIG_PATH = PROJECT / "code" / "config.yaml"
CORRECTIONS = {
    "02355HS6_0236HS5_20260408_134217": {"name": "0235HS6_0236HS5_20260408_134217", "reason": "An extra 5."},
    "0235HS6_0237HS6_20260425_132118": {"name": "0235HS5_0237HS6_20260425_132118", "reason": "Both on HS6."},
    REC_STEM: {"merged": {"0236HS3": "0236HS3/misnamed_merged.rec"}, "reason": "Named for another animal."},
}


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
        ("0235HS3_0237HS4_Session1_20260308_142653", "20260308T142653"),
        ("0235HS3_0237HS4_sess1_20260318_111532", "20260318T111532"),
        ("0235HS4_0236HS3_Sess1_20260318_102354", "20260318T102354"),
        ("0235HS5_0236HS8_Merge20260423_142917", "20260423T142917"),
    ],
)
def test_derive_session_label(stem, expected):
    assert core.derive_session_label(stem) == expected


def test_derive_subject_labels_keeps_basename_order():
    headstages = core.derive_subject_labels(REC_STEM)
    assert [(h.subject, h.headstage, h.position) for h in headstages] == [("0236", "3", 0), ("0237", "4", 1)]


@pytest.mark.parametrize(
    "stem",
    [
        "notes",
        "0236_0237_20260401",
        "0236HS3-0237HS4_20260401_130419",
        "0236HS3_0237HS4_RecordingTest1_20260223_155333",
        "02355HS6_0236HS5_20260408_134217",
    ],
)
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


def test_parse_rec_identity_applies_a_name_correction(tmp_path):
    stem = "02355HS6_0236HS5_20260408_134217"
    rec_dir = make_rec_dir(tmp_path, pair="0235-0236", date_dirname="04.08.2026", stem=stem)
    with pytest.raises(ValueError, match="not a recognized recording name"):
        core.parse_rec_identity(rec_dir)
    identity = core.parse_rec_identity(rec_dir, corrections=CORRECTIONS)
    assert [headstage.tag for headstage in identity.headstages] == ["0235HS6", "0236HS5"]
    assert identity.session_label == "20260408T134217"
    assert identity.rec_path == rec_dir / f"{stem}.rec"
    assert identity.correction_reason == "An extra 5."


@pytest.mark.parametrize(
    ("uploaded", "correction", "message"),
    [
        (REC_STEM, {"reason": "Checked.", "note": "Typo."}, "unknown keys"),
        (REC_STEM, {"merged": {"0236HS3": "0236HS3/file_merged.rec"}}, "gives no reason"),
        ("02355HS6_0236HS5_20260408_134217", {"reason": "Checked."}, "unrecognized recording"),
        (REC_STEM, {"merged": {"0235HS6": "0235HS6/file_merged.rec"}, "reason": "Checked."}, "not headstages"),
    ],
)
def test_recording_corrections_rejects_malformed_entries(uploaded, correction, message):
    with pytest.raises(ValueError, match=message):
        core.recording_corrections({"corrections": {uploaded: correction}})


def test_config_corrections_are_well_formed():
    corrections = core.recording_corrections(core.load_cfg(CONFIG_PATH))
    assert corrections
    assert all(correction["reason"] for correction in corrections.values())


@pytest.mark.parametrize("pair", ["0236-0237", "0235-0237"])
@pytest.mark.parametrize("date_dirname", ["04.01.2026", "04.01.2026/Session_1"])
def test_parse_rec_identity_checks_pair_through_session_folders(tmp_path, pair, date_dirname):
    rec_dir = make_rec_dir(tmp_path, pair=pair, date_dirname=date_dirname)
    if pair == "0236-0237":
        assert core.parse_rec_identity(rec_dir).pair == pair
    else:
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


@pytest.mark.parametrize(
    "calibration", ["cam14-cal-04012026121856-0000.avi", "Cam14-Calibration-04012026121856-0000.avi"]
)
@pytest.mark.parametrize("date_dirname", ["04.01.2026", "04.01.2026/Session_2"])
def test_match_videos_picks_nearest_stamp_per_camera(tmp_path, calibration, date_dirname):
    rec_dir = make_rec_dir(tmp_path, date_dirname=date_dirname)
    videos = rec_dir.parent / "Videos"
    videos.mkdir()
    for name in [
        "cam14-04012026122439-0000.avi",
        "cam14-04012026162439-0000.avi",
        calibration,
        "cam46-04012026122433-0000.avi",
        "README.txt",
    ]:
        (videos / name).write_bytes(b"")
    matched, unmatched = core.match_videos(core.parse_rec_identity(rec_dir))
    assert matched[14]["video"].name == "cam14-04012026122439-0000.avi"
    assert matched[14]["calibration"].name == calibration
    assert matched[46] == {"video": videos / "cam46-04012026122433-0000.avi"}
    assert [path.name for path in unmatched] == ["README.txt"]


def test_match_videos_without_videos_dir(tmp_path):
    matched, unmatched = core.match_videos(core.parse_rec_identity(make_rec_dir(tmp_path)))
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


@pytest.mark.parametrize("position", [0, 1])
def test_headstage_channel_ids_single_headstage_file(position):
    channel_ids = [str(channel) for channel in range(32)]
    selected = core.headstage_channel_ids(channel_ids=channel_ids, position=position, channels_per_headstage=32)
    assert selected == channel_ids


def test_merged_rec_path(tmp_path):
    rec_dir = make_rec_dir(tmp_path)
    identity = core.parse_rec_identity(rec_dir)
    paths = [core.merged_rec_path(identity=identity, headstage=headstage) for headstage in identity.headstages]
    assert paths == [
        rec_dir / "0236HS3" / f"{REC_STEM}_0236HS3_merged.rec",
        rec_dir / "0237HS4" / f"{REC_STEM}_0237HS4_merged.rec",
    ]


def test_merged_rec_path_accepts_a_missing_underscore(tmp_path):
    rec_dir = make_rec_dir(tmp_path)
    identity = core.parse_rec_identity(rec_dir)
    written = rec_dir / "0237HS4" / f"{REC_STEM}_0237HS4merged.rec"
    written.parent.mkdir()
    written.write_bytes(b"")
    paths = [core.merged_rec_path(identity=identity, headstage=headstage) for headstage in identity.headstages]
    assert paths == [rec_dir / "0236HS3" / f"{REC_STEM}_0236HS3_merged.rec", written]


@pytest.mark.parametrize("in_folder", [False, True])
def test_merged_rec_path_finds_merged_files_loose_in_the_recording_folder(tmp_path, in_folder):
    rec_dir = make_rec_dir(tmp_path)
    identity = core.parse_rec_identity(rec_dir)
    loose = [rec_dir / f"{REC_STEM}_{headstage.tag}_merged.rec" for headstage in identity.headstages]
    for path in loose:
        path.write_bytes(b"")
    expected = loose
    if in_folder:
        expected = [rec_dir / headstage.tag / path.name for headstage, path in zip(identity.headstages, loose)]
        for path in expected:
            path.parent.mkdir()
            path.write_bytes(b"")
    paths = [core.merged_rec_path(identity=identity, headstage=headstage) for headstage in identity.headstages]
    assert paths == expected


@pytest.mark.parametrize(
    ("pair", "uploaded", "merged_stem"),
    [
        ("0235-0236", "02355HS6_0236HS5_20260408_134217", "02355HS6_0236HS5_20260408_134217"),
        ("0235-0237", "0235HS6_0237HS6_20260425_132118", "0235HS5_0237HS6_20260425_132118"),
    ],
)
def test_merged_rec_path_reads_the_uploaded_or_corrected_name(tmp_path, pair, uploaded, merged_stem):
    rec_dir = make_rec_dir(tmp_path, pair=pair, stem=uploaded)
    identity = core.parse_rec_identity(rec_dir, corrections=CORRECTIONS)
    written = [
        rec_dir / headstage.tag / f"{merged_stem}_{headstage.tag}_merged.rec" for headstage in identity.headstages
    ]
    for path in written:
        path.parent.mkdir()
        path.write_bytes(b"")
    paths = [core.merged_rec_path(identity=identity, headstage=headstage) for headstage in identity.headstages]
    assert paths == written


@pytest.mark.parametrize("renamed_by_lab", [False, True])
def test_merged_rec_path_takes_a_corrected_file_while_it_exists(tmp_path, renamed_by_lab):
    rec_dir = make_rec_dir(tmp_path)
    identity = core.parse_rec_identity(rec_dir, corrections=CORRECTIONS)
    misnamed = rec_dir / "0236HS3" / "misnamed_merged.rec"
    standard = rec_dir / "0236HS3" / f"{REC_STEM}_0236HS3_merged.rec"
    present = standard if renamed_by_lab else misnamed
    present.parent.mkdir()
    present.write_bytes(b"")
    assert core.merged_rec_path(identity=identity, headstage=identity.headstages[0]) == present


def test_session_notes_record_a_correction(tmp_path):
    cfg = core.load_cfg(CONFIG_PATH)
    rec_dir = make_rec_dir(tmp_path)
    plain = core.session_notes(identity=core.parse_rec_identity(rec_dir), session_row=None, cfg=cfg)
    corrected = core.session_notes(
        identity=core.parse_rec_identity(rec_dir, corrections=CORRECTIONS), session_row=None, cfg=cfg
    )
    assert plain == "Pair 0236-0237. Session log usable data: not logged. Session log notes: none."
    assert corrected == f"{plain} Source names corrected for {rec_dir.name}: Named for another animal."


def test_convert_session_fails_before_placing_videos_without_merged_ephys(tmp_path, monkeypatch):
    rec_dir = make_rec_dir(tmp_path)
    placed = []
    monkeypatch.setattr(core, "place_videos", lambda **kwargs: placed.append(kwargs))
    cfg = core.load_cfg(PROJECT / "code" / "config.yaml")
    with pytest.raises(FileNotFoundError, match="0236HS3_merged.rec"):
        core.convert_session(rec=rec_dir, output_dir=tmp_path / "out", cfg=cfg)
    assert placed == []


def test_discover_recordings_reports_strays(tmp_path):
    first = make_rec_dir(tmp_path)
    second = make_rec_dir(tmp_path, pair="0235-0237", stem="0235HS1_0237HS4_20260401_150800")
    (first.parent / "Videos").mkdir()
    (first.parent / "scratch").mkdir()
    (first.parent / "notes.txt").write_text("stray\n")
    recordings, ignored = batch_convert.discover_recordings(tmp_path)
    assert recordings == [second, first]
    assert [path.name for path in ignored] == ["notes.txt", "scratch"]


def test_discover_recordings_reads_session_folders(tmp_path):
    first = make_rec_dir(tmp_path, date_dirname="04.23.2026/Session_1", stem="0236HS7_0237HS8_20260423_103710")
    second = make_rec_dir(tmp_path, date_dirname="04.23.2026/Session2", stem="0236HS6_0237HS7_sess2_20260423_153827")
    (first.parent / "Videos").mkdir()
    (second.parent / "notes.txt").write_text("stray\n")
    recordings, ignored = batch_convert.discover_recordings(tmp_path)
    assert recordings == [second, first]
    assert ignored == [second.parent / "notes.txt"]


def test_convert_batch_applies_config_corrections(tmp_path, monkeypatch, capsys):
    rec_dir = make_rec_dir(
        tmp_path, pair="0235-0236", date_dirname="04.08.2026", stem="02355HS6_0236HS5_20260408_134217"
    )
    calls = []
    monkeypatch.setattr(batch_convert, "convert_session", lambda **kwargs: calls.append(kwargs["rec"]) or [])
    exit_code = batch_convert.convert_batch(
        incoming_dir=tmp_path, standardized_dir=tmp_path / "out", config_path=CONFIG_PATH, max_workers=1
    )
    assert exit_code == 0
    assert calls == [rec_dir]
    assert "unrecognized" not in capsys.readouterr().out


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


def test_results_split_missing_inputs_from_failures(tmp_path, monkeypatch):
    converts = make_rec_dir(tmp_path)
    missing = make_rec_dir(tmp_path, date_dirname="04.02.2026", stem="0236HS3_0237HS4_20260402_130419")
    breaks = make_rec_dir(tmp_path, pair="0235-0237", stem="0235HS1_0237HS4_20260401_150800")

    def fake_convert(*, rec, output_dir, cfg, session_log=None, overwrite=False):
        if Path(rec) == missing:
            raise core.MissingInputError("no merged ephys file at somewhere")
        if Path(rec) == breaks:
            raise ValueError("bad header")
        return []

    monkeypatch.setattr(batch_convert, "convert_session", fake_convert)
    results_path = tmp_path / "record" / "results.json"

    exit_code = batch_convert.convert_batch(
        incoming_dir=tmp_path,
        standardized_dir=tmp_path / "out",
        config_path=PROJECT / "code" / "config.yaml",
        max_workers=1,
        results_path=results_path,
    )

    assert exit_code == 1
    assert json.loads(results_path.read_text()) == {
        "pending": {missing.name: "no merged ephys file at somewhere"},
        "failed": {breaks.name: "bad header"},
    }
    assert converts.name not in results_path.read_text()


@pytest.mark.parametrize(
    ("requested", "task_count", "expected"),
    [(None, 1, 1), (None, 10, min(batch_convert.DEFAULT_JOBS, os.cpu_count() or 1)), (8, 3, 3), (1, 5, 1)],
)
def test_resolve_worker_count(requested, task_count, expected):
    assert batch_convert.resolve_worker_count(requested=requested, task_count=task_count) == expected


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
