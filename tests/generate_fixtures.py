#!/usr/bin/env python3
"""(Re)generate the integration-test fixtures.

Creates a small but faithful mock of the raw input tree under
``tests/example_raw/`` and then runs the converter to (re)build the golden
``tests/expected_output/`` tree that the integration test compares against.

The media are generated with the ``ffmpeg`` binary bundled by
``imageio-ffmpeg`` so no system FFmpeg is required, and probed through the
PyAV-backed ``tests/ffprobe_shim.py`` so the golden output is deterministic and
reproducible anywhere the ``dev`` extra is installed.

Run from the repo root::

    python3 tests/generate_fixtures.py

Only run this when you intentionally want to update the committed fixtures.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
sys.path.insert(0, str(REPO / "code"))

import convert_raw_to_bids as conv  # noqa: E402

EXAMPLE_RAW = TESTS / "example_raw"
EXPECTED_OUTPUT = TESTS / "expected_output"
SHIM = TESTS / "ffprobe_shim.py"

# A fixed acquisition time is baked into the video so scans.tsv acq_time is
# deterministic; the images have no embedded time and fall back to the session date.
CREATION_TIME = "2026-07-10T14:23:01.000000Z"

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
    subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", *args], check=True)


def build_example_raw() -> None:
    if EXAMPLE_RAW.exists():
        shutil.rmtree(EXAMPLE_RAW)
    beh = EXAMPLE_RAW / "07102026-Session1" / "overhead" / "beh"
    beh.mkdir(parents=True)

    # Overhead video: small, deterministic, 1 s @ 30 fps, h264/yuv420p, no audio.
    _run_ffmpeg([
        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=30:duration=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-metadata", f"creation_time={CREATION_TIME}",
        "-y", str(beh / "overhead_video.mp4"),
    ])
    # Two still images derived from the overhead view.
    for name in ("average_overhead_video.png", "single_frame.png"):
        _run_ffmpeg(["-f", "lavfi", "-i", "testsrc=size=160x120", "-frames:v", "1",
                     "-y", str(beh / name)])

    # Non-media companions: the .settings feeds the sidecar; the rest are ignored.
    (beh / "overhead_video.settings").write_text(SETTINGS_BODY)
    (beh / "notes.txt").write_text("Overhead recording of a herd of ~25 sheep; free movement.\n")
    (beh / "overhead_dji_metadata.srt").write_text(
        "1\n00:00:00,000 --> 00:00:00,033\n<font>GPS(-83.7,42.3) BAROMETER:0.0m</font>\n"
    )
    (beh / "overhead_video.pv").write_text("(opaque tracker point-view data)\n")
    (beh / "overhead_video.results").write_text("(opaque tracker results)\n")


def build_expected_output() -> None:
    if EXPECTED_OUTPUT.exists():
        shutil.rmtree(EXPECTED_OUTPUT)
    SHIM.chmod(SHIM.stat().st_mode | stat.S_IEXEC | stat.S_IRUSR)
    converter = conv.Converter(
        raw_dir=EXAMPLE_RAW,
        bids_dir=EXPECTED_OUTPUT,
        ffprobe_bin=str(SHIM),
        species="Ovis aries",
        authors=["Kemere Lab"],
    )
    code = converter.run()
    if code != 0:
        raise SystemExit(f"converter failed with exit code {code}")


if __name__ == "__main__":
    build_example_raw()
    build_expected_output()
    print(f"\nFixtures written:\n  {EXAMPLE_RAW}\n  {EXPECTED_OUTPUT}")
