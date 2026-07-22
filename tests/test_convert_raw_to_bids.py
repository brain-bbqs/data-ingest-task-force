#!/usr/bin/env python3
"""End-to-end and unit tests for ``code/convert_raw_to_bids.py``.

Real media fixtures are generated with the ``ffmpeg`` binary bundled by
``imageio-ffmpeg`` and probed through ``tests/ffprobe_shim.py`` (PyAV-backed),
so the converter's real ffprobe-parsing code path is exercised without needing
a system ffprobe install.

Run with::

    python3 -m pytest tests/ -q
    # or standalone:
    python3 tests/test_convert_raw_to_bids.py
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "code"))

import convert_raw_to_bids as conv  # noqa: E402

SHIM = REPO_ROOT / "tests" / "ffprobe_shim.py"

SETTINGS_BODY = """\
calculate_posture = false
cm_per_pixel = 3.687
detect_size_filter = [[10,100000]]
detect_threshold = 15
detect_type = background_subtraction
meta_encoding = rgb8
meta_real_width = 3840
meta_source_path = "/Users/ckemere/Data/Sheep/Michigan-July-2026/07102026-Session1/overhead/beh/overhead_video.mp4"
track_background_subtraction = true
track_max_individuals = 25
track_max_speed = 960
video_conversion_range = [0,99613]
"""


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run_ffmpeg(args: list[str]) -> None:
    subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", *args],
                   check=True)


def _make_shim_executable() -> str:
    SHIM.chmod(SHIM.stat().st_mode | stat.S_IEXEC | stat.S_IRUSR)
    return str(SHIM)


def build_raw_tree(root: Path, *, with_audio: bool = False) -> Path:
    """Create a raw tree mirroring the dandiset 000477 example."""
    beh = root / "07102026-Session1" / "overhead" / "beh"
    beh.mkdir(parents=True)

    video = beh / "overhead_video.mp4"
    if with_audio:
        _run_ffmpeg([
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-c:a", "aac", "-shortest", "-y", str(video),
        ])
    else:
        _run_ffmpeg([
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-y", str(video),
        ])

    # Two still images.
    _run_ffmpeg(["-f", "lavfi", "-i", "testsrc=size=320x240", "-frames:v", "1",
                 "-y", str(beh / "average_overhead_video.png")])
    _run_ffmpeg(["-f", "lavfi", "-i", "testsrc=size=320x240", "-frames:v", "1",
                 "-y", str(beh / "single_frame.png")])

    # Sidecar settings + assorted non-media files that must be ignored.
    (beh / "overhead_video.settings").write_text(SETTINGS_BODY)
    (beh / "notes.txt").write_text("free play, herd of 25\n")
    (beh / "overhead_dji_metadata.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nGPS\n")
    (beh / "overhead_video.pv").write_text("binary-ish\n")
    (beh / "overhead_video.results").write_text("results\n")
    return root


def convert(tmp_path: Path, **kwargs) -> tuple[int, conv.Converter]:
    raw = build_raw_tree(tmp_path / "raw", with_audio=kwargs.pop("with_audio", False))
    bids = tmp_path / "rawbids"
    converter = conv.Converter(
        raw_dir=raw, bids_dir=bids, ffprobe_bin=_make_shim_executable(),
        species="Ovis aries", **kwargs,
    )
    return converter.run(), converter


# --------------------------------------------------------------------------- #
# Pure-function unit tests
# --------------------------------------------------------------------------- #

def test_parse_settings_types():
    parsed = conv.parse_settings(SETTINGS_BODY)
    assert parsed["calculate_posture"] is False
    assert parsed["cm_per_pixel"] == 3.687
    assert parsed["detect_size_filter"] == [[10, 100000]]
    assert parsed["detect_threshold"] == 15
    assert parsed["detect_type"] == "background_subtraction"
    assert parsed["meta_encoding"] == "rgb8"
    assert parsed["meta_real_width"] == 3840
    assert parsed["track_background_subtraction"] is True
    assert parsed["track_max_individuals"] == 25
    assert parsed["video_conversion_range"] == [0, 99613]
    assert parsed["meta_source_path"].endswith("overhead_video.mp4")


def test_parse_settings_edge_cases():
    body = "# comment\n\nempty =\nnums = [1, 2, 3]\nquoted = \"hello world\"\nbare = foo_bar\nnegative = -12.5\n"
    parsed = conv.parse_settings(body)
    assert parsed["empty"] == ""
    assert parsed["nums"] == [1, 2, 3]
    assert parsed["quoted"] == "hello world"
    assert parsed["bare"] == "foo_bar"
    assert parsed["negative"] == -12.5
    assert "comment" not in parsed


@pytest.mark.parametrize("name,expected", [
    ("07102026-Session1", "20260710"),
    ("07102026-Session2", "20260710s02"),
    ("07102026-Session10", "20260710s10"),
    ("12312025-Session1", "20251231"),
    ("07102026_Session1", "20260710"),
    ("random-folder", "randomfolder"),
])
def test_session_labels(name, expected):
    assert conv.derive_session_label(name).label == expected


def test_frame_rate():
    assert abs(conv.parse_frame_rate("30000/1001") - 29.97002997) < 1e-6
    assert conv.parse_frame_rate("25/1") == 25.0
    assert conv.parse_frame_rate("0/0") is None
    assert conv.parse_frame_rate(None) is None


def test_rfc6381():
    assert conv.rfc6381_video(
        {"codec_name": "h264", "profile": "High", "level": 40, "codec_tag_string": "avc1"}
    ) == "avc1.640028"
    assert conv.rfc6381_video(
        {"codec_name": "h264", "profile": "Main", "level": 31}
    ) == "avc1.4d001f"
    assert conv.rfc6381_video({"codec_name": "hevc", "profile": "Main", "level": 120}) is None
    assert conv.rfc6381_audio({"codec_name": "aac", "profile": "LC"}) == "mp4a.40.2"


def test_build_stem_entity_order():
    ents = {"sub": "multi", "ses": "20260710", "acq": "average", "recording": "overhead"}
    assert conv.build_stem(ents, "image") == \
        "sub-multi_ses-20260710_acq-average_recording-overhead_image"
    ents2 = {"sub": "multi", "ses": "20260710", "recording": "overhead"}
    assert conv.build_stem(ents2, "video") == "sub-multi_ses-20260710_recording-overhead_video"


def test_image_acq_label():
    assert conv.image_acq_label("average_overhead_video", "overhead") == "average"
    assert conv.image_acq_label("single_frame", "overhead") == "singleframe"


def test_recording_from_path(tmp_path):
    session = tmp_path / "07102026-Session1"
    media = session / "overhead" / "beh" / "overhead_video.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"x")
    assert conv.recording_label_from_path(session, media) == "overhead"


# --------------------------------------------------------------------------- #
# End-to-end tests
# --------------------------------------------------------------------------- #

def test_end_to_end_video_only(tmp_path):
    code, converter = convert(tmp_path)
    assert code == 0
    bids = converter.bids_dir

    # Dataset-level files.
    desc = json.loads((bids / "dataset_description.json").read_text())
    assert desc["BIDSVersion"] == conv.BIDS_VERSION
    assert desc["DatasetType"] == "raw"
    assert (bids / "README").is_file()
    assert "Ovis aries" in (bids / "participants.tsv").read_text()
    assert (bids / "participants.json").is_file()

    beh = bids / "sub-multi" / "ses-20260710" / "beh"
    video = beh / "sub-multi_ses-20260710_recording-overhead_video.mp4"
    assert video.is_file(), sorted(p.name for p in beh.iterdir())

    sidecar = json.loads((beh / "sub-multi_ses-20260710_recording-overhead_video.json").read_text())
    assert sidecar["VideoCodec"] == "h264"
    assert round(sidecar["VideoFrameRate"]) == 30
    assert sidecar["VideoFrameCount"] == 30
    assert sidecar["ImageWidth"] == 320
    assert sidecar["ImageHeight"] == 240
    assert sidecar["ImagePixelFormat"] == "yuv420p"
    assert sidecar["ImageBitDepth"] == 8
    assert sidecar["RecordingDuration"] == pytest.approx(1.0, abs=0.2)
    assert sidecar["DevicePosition"] == "overhead"
    # No audio fields on a video-only recording.
    assert "AudioCodec" not in sidecar
    # Settings provenance block.
    params = sidecar["TrackingSettings"]["Parameters"]
    assert params["cm_per_pixel"] == 3.687
    assert params["track_max_individuals"] == 25

    # Two images with distinct acq labels.
    avg = beh / "sub-multi_ses-20260710_acq-average_recording-overhead_image.png"
    single = beh / "sub-multi_ses-20260710_acq-singleframe_recording-overhead_image.png"
    assert avg.is_file()
    assert single.is_file()
    img_sidecar = json.loads(
        (beh / "sub-multi_ses-20260710_acq-average_recording-overhead_image.json").read_text())
    assert img_sidecar["ImageWidth"] == 320
    assert img_sidecar["ImageHeight"] == 240
    assert "RecordingDuration" not in img_sidecar
    assert "VideoCodec" not in img_sidecar

    # scans.tsv with participant-relative paths.
    scans = (bids / "sub-multi" / "ses-20260710" / "sub-multi_ses-20260710_scans.tsv").read_text()
    assert "filename\tacq_time" in scans
    assert "ses-20260710/beh/sub-multi_ses-20260710_recording-overhead_video.mp4" in scans


def test_end_to_end_audiovideo(tmp_path):
    code, converter = convert(tmp_path, with_audio=True)
    assert code == 0
    beh = converter.bids_dir / "sub-multi" / "ses-20260710" / "beh"
    av_file = beh / "sub-multi_ses-20260710_recording-overhead_audiovideo.mp4"
    assert av_file.is_file(), sorted(p.name for p in beh.iterdir())
    sidecar = json.loads(
        (beh / "sub-multi_ses-20260710_recording-overhead_audiovideo.json").read_text())
    assert sidecar["AudioCodec"] == "aac"
    assert sidecar["AudioChannelCount"] >= 1
    assert sidecar["AudioSampleRate"] > 0
    assert sidecar["VideoCodec"] == "h264"


def test_non_media_files_ignored(tmp_path):
    code, converter = convert(tmp_path)
    assert code == 0
    ignored = {p.name for p in converter.skipped_files}
    assert {"notes.txt", "overhead_dji_metadata.srt",
            "overhead_video.pv", "overhead_video.results"} <= ignored
    # The .settings file is consumed (merged), not "ignored".
    assert "overhead_video.settings" not in ignored


def test_dry_run_writes_nothing(tmp_path):
    code, converter = convert(tmp_path, dry_run=True)
    assert code == 0
    assert not converter.bids_dir.exists()
    assert converter.converted == 3  # 1 video + 2 images planned


def test_skip_metadata(tmp_path):
    code, converter = convert(tmp_path, skip_metadata=True)
    assert code == 0
    beh = converter.bids_dir / "sub-multi" / "ses-20260710" / "beh"
    sidecar = json.loads(
        (beh / "sub-multi_ses-20260710_recording-overhead_video.json").read_text())
    # No ffprobe -> only settings + device position.
    assert "VideoCodec" not in sidecar
    assert sidecar["DevicePosition"] == "overhead"
    assert "TrackingSettings" in sidecar


def test_same_label_folders_do_not_clobber(tmp_path):
    """Two distinct raw folders that resolve to the same session label must
    both survive without overwriting each other's outputs."""
    raw = tmp_path / "raw"
    for folder in ("bad-name", "bad_name"):  # both sanitize to 'badname'
        beh = raw / folder / "overhead" / "beh"
        beh.mkdir(parents=True)
        (beh / "single_frame.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    bids = tmp_path / "rawbids"
    converter = conv.Converter(raw_dir=raw, bids_dir=bids, skip_metadata=True)
    assert converter.run() == 0
    images = sorted(
        (bids / "sub-multi" / "ses-badname" / "beh").glob("*.png")
    )
    assert len(images) == 2, [p.name for p in images]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
