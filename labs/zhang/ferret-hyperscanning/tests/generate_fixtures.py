#!/usr/bin/env python3
"""Generate the committed fixtures for the integration test.

Writes ``tests/example_raw/``, a tiny but structurally faithful stand-in for
one uploaded recording (see ``code/README.md`` for the real layout): a
synthetic SpikeGadgets ``.rec`` with two 32-channel headstages and a camera
frame pulse on a digital input, plus ten small AVI files named like the
lab's behavior and calibration videos. Then runs the converter over it and
writes ``tests/expected_output/summary.json``, the golden structural
summary the integration test compares against.

All values are deterministic so regenerating the fixture is reproducible.

Run with::

    python3 tests/generate_fixtures.py
"""

from __future__ import annotations

import json
import shutil
import struct
import sys
from pathlib import Path

import av
import numpy

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(PROJECT / "code"))

import batch_convert  # noqa: E402
from nwb_summary import summarize_output_tree  # noqa: E402

EXAMPLE_RAW = TESTS / "example_raw"
EXPECTED_OUTPUT = TESTS / "expected_output"
CONFIG = PROJECT / "code" / "config.yaml"

REC_STEM = "0236HS3_0237HS4_20260401_130419"
PAIR = "0236-0237"
DATE_DIRNAME = "04.01.2026"
CAMERAS = (14, 46, 58, 67, 68)
VIDEO_STAMPS = {
    14: "04012026122439",
    46: "04012026122433",
    58: "04012026122436",
    67: "04012026122443",
    68: "04012026122430",
}
CALIBRATION_STAMPS = {
    14: "04012026121856",
    46: "04012026121851",
    58: "04012026121853",
    67: "04012026121854",
    68: "04012026121850",
}
# 2026-04-01T13:04:19-04:00, matching the basename, as Trodes stores it (ms since the epoch).
SYSTEM_TIME_AT_CREATION_MS = 1775063059000
SAMPLING_RATE = 20000
CHANNELS_PER_CHIP = 32
CHIP_COUNT = 2
PACKET_COUNT = 200
FRAME_PERIOD_PACKETS = 667
VIDEO_FRAMES = {"video": 6, "calibration": 3}
FRAME_WIDTH = 16
FRAME_HEIGHT = 12


def write_synthetic_rec(path, /):
    """A minimal Trodes file: XML configuration, then fixed-size packets neo can parse."""
    trodes = []
    for chip in range(CHIP_COUNT):
        channels = "".join(
            f'<SpikeChannel hwChan="{chip * CHANNELS_PER_CHIP + channel}"/>' for channel in range(CHANNELS_PER_CHIP)
        )
        trodes.append(f'<SpikeNTrode id="{chip + 1}" spikeScalingToUv="0.195">{channels}</SpikeNTrode>')
    channel_count = CHANNELS_PER_CHIP * CHIP_COUNT
    header = (
        "<Configuration>\n"
        f'<GlobalConfiguration systemTimeAtCreation="{SYSTEM_TIME_AT_CREATION_MS}" timestampAtCreation="0" '
        f'filePrefix="{REC_STEM}"/>\n'
        f'<HardwareConfiguration samplingRate="{SAMPLING_RATE}" numChannels="{channel_count}">\n'
        '<Device name="ECU" numBytes="4"><Channel id="Din1" dataType="digital" startByte="0" bit="0"/></Device>\n'
        "</HardwareConfiguration>\n"
        f'<SpikeConfiguration device="intan" chanPerChip="{CHANNELS_PER_CHIP}">{"".join(trodes)}</SpikeConfiguration>\n'
        "</Configuration>\n"
    )
    rng = numpy.random.default_rng(0)
    with open(path, "wb") as handle:
        handle.write(header.encode())
        for index in range(PACKET_COUNT):
            handle.write(b"\x55")
            handle.write(struct.pack("<I", 1 if index % FRAME_PERIOD_PACKETS == 0 else 0))
            handle.write(struct.pack("<I", index))
            handle.write(rng.integers(-2000, 2000, channel_count, dtype="<i2").tobytes())


def write_synthetic_avi(path, /, *, frames):
    with av.open(str(path), "w") as container:
        stream = container.add_stream("rawvideo", rate=30)
        stream.width = FRAME_WIDTH
        stream.height = FRAME_HEIGHT
        stream.pix_fmt = "gray"
        for index in range(frames):
            pixels = numpy.full((FRAME_HEIGHT, FRAME_WIDTH), index * 10, dtype=numpy.uint8)
            frame = av.VideoFrame.from_ndarray(pixels, format="gray")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def build_example_raw():
    if EXAMPLE_RAW.exists():
        shutil.rmtree(EXAMPLE_RAW)
    date_dir = EXAMPLE_RAW / batch_convert.RAW_SUBTREE / PAIR / DATE_DIRNAME
    rec_dir = date_dir / f"{REC_STEM}.rec"
    rec_dir.mkdir(parents=True)
    write_synthetic_rec(rec_dir / f"{REC_STEM}.rec")
    videos_dir = date_dir / "Videos"
    videos_dir.mkdir()
    for camera in CAMERAS:
        write_synthetic_avi(videos_dir / f"cam{camera}-{VIDEO_STAMPS[camera]}-0000.avi", frames=VIDEO_FRAMES["video"])
        write_synthetic_avi(
            videos_dir / f"cam{camera}-cal-{CALIBRATION_STAMPS[camera]}-0000.avi", frames=VIDEO_FRAMES["calibration"]
        )
    (videos_dir / "notes.txt").write_text("stray file the converter must report and ignore\n")


def build_expected_output(scratch_dir, /):
    exit_code = batch_convert.convert_batch(
        incoming_dir=EXAMPLE_RAW, standardized_dir=scratch_dir, config_path=CONFIG, overwrite=True, max_workers=1
    )
    if exit_code != 0:
        raise RuntimeError("conversion of the example fixture failed")
    summary = summarize_output_tree(scratch_dir)
    EXPECTED_OUTPUT.mkdir(parents=True, exist_ok=True)
    (EXPECTED_OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


def main():
    build_example_raw()
    print(f"Wrote {EXAMPLE_RAW}")
    scratch_dir = TESTS / "_scratch_output"
    if scratch_dir.exists():
        shutil.rmtree(scratch_dir)
    try:
        build_expected_output(scratch_dir)
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
    print(f"Wrote {EXPECTED_OUTPUT / 'summary.json'}")


if __name__ == "__main__":
    main()
