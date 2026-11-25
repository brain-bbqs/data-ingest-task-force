#!/usr/bin/env python3
"""(Re)generate the integration-test fixtures.

Builds a small mock of dandiset 000641 under ``tests/example_raw/`` with one MouseDyad-10M collection
(two sessions) and one SLAP-2M collection (one session), then runs the converter to rebuild the golden
trees under ``tests/expected_output/``.

The mock is generated, not lab data. File names, folder layout, HDF5 dataset names and the text formats
follow the real deposit. Camera counts and array sizes are cut down so the fixtures stay small.

Videos are made with the ``ffmpeg`` binary bundled by ``imageio-ffmpeg`` and probed through the
PyAV-backed ``tests/ffprobe_shim.py``, so the golden output is reproducible wherever the ``dev`` extra
is installed.

Run from ``labs/talmo/``::

    python3 tests/generate_fixtures.py

Only run this when you intend to update the committed fixtures.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import h5py
import imageio_ffmpeg
import numpy

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "code"))

import convert_luc3d_to_bids as conv  # noqa: E402

EXAMPLE_RAW = TESTS / "example_raw"
EXPECTED_OUTPUT = TESTS / "expected_output"
SHIM = TESTS / "ffprobe_shim.py"
CONFIG = TESTS.parent / "code" / "config.yaml"
DATASETS = ("mouse-dyad-10m", "slap-2m")

NODES = [
    "Nose",
    "Ear_R",
    "Ear_L",
    "TTI",
    "TailTip",
    "Head",
    "Trunk",
    "Tail_0",
    "Tail_1",
    "Tail_2",
    "Shoulder_left",
    "Shoulder_right",
    "Haunch_left",
    "Haunch_right",
    "Neck",
]
SKELETON_TOML = (
    "nodes = [ " + ", ".join(f'"{node}"' for node in NODES) + ",]\n"
    'edges = [ [ "TTI", "Head",], [ "Head", "Nose",],]\n'
    "edge_idxs = [ [ 3, 5,], [ 5, 0,],]\n"
)
FRAMES = 5


def write_video(*, path: Path, rate: str, pixel_format: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=64x48:rate={rate}",
        "-frames:v",
        str(FRAMES),
        "-c:v",
        "libx264",
        "-profile:v",
        "high",
        "-pix_fmt",
        pixel_format,
        "-bitexact",
        "-y",
        str(path),
    ]
    subprocess.run(command, check=True)


def camera_table(*, index: int, name: str) -> str:
    table = (
        f"[cam_{index}]\n"
        f'name = "{name}"\n'
        "size = [ 64, 48,]\n"
        f"matrix = [ [ {100.5 + index}, 0.0, 31.5,], [ 0.0, {100.5 + index}, 23.5,], [ 0.0, 0.0, 1.0,],]\n"
        "distortions = [ -0.2, 0.0, 0.0, 0.0, 0.0,]\n"
        f"rotation = [ 0.1, {0.2 * index}, 0.3,]\n"
        f"translation = [ {10.0 * index}, 20.0, 30.0,]\n\n"
    )
    return table


def write_calibration(*, path: Path, cameras: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(camera_table(index=index, name=name) for index, name in enumerate(cameras))
    path.write_text(text + "[metadata]\nadjusted = false\nerror = 0.5\n")


def write_slp(*, path: Path, video_name: str, tracks: list[str], provenance: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {"version": "2.0.0", "skeletons": [], "nodes": [], "provenance": provenance}
    frame_type = numpy.dtype([("frame_id", "<u8"), ("video", "<u4"), ("frame_idx", "<u8")])
    with h5py.File(path, "w") as file:
        file.create_group("metadata").attrs["json"] = numpy.bytes_(json.dumps(metadata))
        videos = [json.dumps({"backend": {"filename": video_name, "grayscale": True}})]
        file.create_dataset("videos_json", data=numpy.array(videos, dtype="S"))
        file.create_dataset("tracks_json", data=numpy.array([json.dumps([0, name]) for name in tracks], dtype="S"))
        file.create_dataset("frames", data=numpy.zeros(FRAMES, dtype=frame_type))
        file.create_dataset("instances", data=numpy.zeros(FRAMES * len(tracks), dtype=[("instance_id", "<i8")]))


def write_analysis(*, path: Path, video_name: str, tracks: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as file:
        file.create_dataset("tracks", data=numpy.zeros((tracks, 2, len(NODES), FRAMES)))
        file.create_dataset("node_names", data=numpy.array(NODES, dtype="S"))
        file.create_dataset("track_names", data=numpy.array([f"track_{index}" for index in range(tracks)], dtype="S"))
        file.create_dataset("video_path", data=video_name)
        file.create_dataset("provenance", data="{}")


def write_points(*, path: Path, shape: tuple[int, ...], description: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as file:
        dataset = file.create_dataset("tracks", data=numpy.zeros(shape))
        if description:
            dataset.attrs["Description"] = description


def build_dyad_session(
    *, root: Path, folder: str, timestamp: str, calibration: str, cameras: list[str], tracks: list[str], full: bool
) -> None:
    session = root / "sessions" / folder
    session.mkdir(parents=True, exist_ok=True)
    with h5py.File(session / f"{timestamp}_points3d_translated_rotated_metric.h5", "w") as file:
        file.create_dataset("tracks", data=numpy.zeros((FRAMES, 2, len(NODES), 3)))
        file.create_dataset("node_names", data=numpy.array(NODES, dtype=object), dtype=h5py.string_dtype())
        file.create_dataset("track_names", data=numpy.array(tracks, dtype=object), dtype=h5py.string_dtype())
        file.create_dataset("recording_frame_rate", data=150.1054)
        file.create_dataset("experimental_code", data="ACL2MSFSd")
    write_calibration(path=session / "calibration" / f"{calibration}_calibration.toml", cameras=cameras)
    if full:
        (session / "calibration" / f"{calibration}_cboard.toml").write_text(
            "board_x = 8\nboard_y = 11\nsquare_length = 24\nmarker_length = 18.75\nmarker_bits = 4\ndict_size = 1000\n"
        )
        with h5py.File(session / "calibration" / f"{calibration}_calibration.metadata.h5", "w") as file:
            corners = file.create_dataset("detected_corners", data=numpy.zeros((len(cameras), 3, 4, 2)))
            corners.attrs["Description"] = f"Shape: (n_cams, n_frames, n_corners, 2). View order: {cameras}."
    for camera in cameras:
        stem = f"{camera}-{timestamp}"
        write_video(path=session / camera / f"{stem}.mp4", rate="150", pixel_format="yuv420p")
        provenance = {"sleap_version": "1.3.3", "predictor": "TopDownPredictor"}
        write_slp(
            path=session / camera / f"{stem}.slp",
            video_name=f"F:/Data/{folder}/{stem}.mp4",
            tracks=["track_0", "track_1"],
            provenance=provenance,
        )
        write_analysis(path=session / camera / f"{stem}.analysis.h5", video_name=f"{stem}.mp4", tracks=2)


def build_dyad(root: Path, /) -> None:
    session = root / "sessions"
    build_dyad_session(
        root=root,
        folder="20250827_141755",
        timestamp="20250827141804",
        calibration="20250821100634",
        cameras=["21241563", "22085397"],
        tracks=["181321_0", "181313_3"],
        full=True,
    )
    # Mirrors the 2025-09-08 sessions, which lack the board and detections files.
    build_dyad_session(
        root=root,
        folder="20250908_152229",
        timestamp="20250908152238",
        calibration="20250904115349",
        cameras=["21241563"],
        tracks=["178621_1", "181315_4"],
        full=False,
    )
    (session / "20250908_152229" / "notes.txt").write_text("A file no mapping rule covers.\n")
    (root / "README.md").write_text("# MouseDyad-10M\n\nMock of the lab README for the integration test.\n")
    (root / "manifest.csv").write_text("path,size_bytes,category\nREADME.md,1,metadata\n")
    (root / "qc_sessions.csv").write_text("session,track_names\n20250827_141755,181321_0|181313_3\n")
    # One count is wrong on purpose, to exercise the frame-count cross-check.
    (root / "qc_views.csv").write_text(
        "session,camera,video_nb_frames\n"
        f"20250827_141755,21241563,{FRAMES}\n"
        f"20250827_141755,22085397,{FRAMES + 1}\n"
        f"20250908_152229,21241563,{FRAMES}\n"
    )
    (root / "mouse_skeleton.toml").write_text(SKELETON_TOML)
    model = root / "models" / "sleap-nn" / "250505_195550.centroid_N_39644"
    model.mkdir(parents=True)
    (model / "training_config.yaml").write_text("model: mock\n")


def build_slap(root: Path, /) -> None:
    folder, date = "10072022120554", "2022-10-07"
    session = root / "sessions" / date / folder
    cameras = {"back": "10072022120551", "side": "10072022120559"}
    session.mkdir(parents=True)
    write_calibration(path=session / "calibration.toml", cameras=list(cameras))
    (session / "alignment.toml").write_text('rotation = [ [ "1.0", "0.0", "0.0",],]\ntranslation = [ "0.0",]\n')
    shape_note = "Shape: (n_frames, n_tracks, n_nodes, 3)."
    write_points(path=session / "points3d.h5", shape=(FRAMES, 1, len(NODES), 3), description=shape_note)
    write_points(path=session / "aligned_points3d.h5", shape=(FRAMES, 1, len(NODES), 3), description=shape_note)
    write_points(path=session / "aligned_cage_points3d.h5", shape=(1, 1, 24, 3), description=shape_note)
    with h5py.File(session / "reprojections.h5", "w") as file:
        for camera in cameras:
            file.create_dataset(camera, data=numpy.zeros((FRAMES, 1, len(NODES), 2)))

    for camera, timestamp in cameras.items():
        directory = session / camera
        prefix = f"{camera}-{timestamp}-0000"
        video_name = f"{prefix}_h264_CRF20_denoised.mp4"
        write_video(path=directory / video_name, rate="30", pixel_format="yuvj420p")
        old = f"{prefix}_h265_CRF30_denoised.mp4"
        write_slp(path=directory / f"{old}.reprojections.slp", video_name=video_name, tracks=["track_0"], provenance={})
        write_analysis(path=directory / f"{old}.reprojections.slp.h5", video_name=video_name, tracks=1)
        if camera == "side":
            write_slp(
                path=directory / f"{prefix}_h265_CRF12_denoised.mp4.predictions.slp",
                video_name=video_name,
                tracks=["track_0", "track_1"],
                provenance={"sleap_nn_version": "0.2.0", "model_type": "bottom_up"},
            )
        else:
            proofread = directory / f"{old}.predictions.proofread.slp"
            write_slp(path=proofread, video_name=video_name, tracks=["track_0"], provenance={})
            write_analysis(path=Path(f"{proofread}.analysis.h5"), video_name=video_name, tracks=1)
            # The real deposit has three such strays, which no mapping rule covers.
            stray = directory / f"{prefix}_h265_CRF12_denoised.mp4.predictions.proofread.slpanalysis.h5"
            write_analysis(path=stray, video_name=video_name, tracks=1)

    header = "\tsession\tsession_path\twhite_mice\tagouti_mice\tblack_mice\tanimals\tobstacle_rating\tbedding\tframes"
    header += "\tduration\tdifficulty\n"
    row = f"0\t{folder}\t{date}/{folder}\t0\t0\t1\t1\t0\tblack\t{FRAMES}\t\t1\n"
    (root / "master_sheet.tsv").write_text(header + row)
    (root / "master_sheet_side_model.tsv").write_text(header + row)
    (root / "README.md").write_text("# SLAP-2M\n\nMock of the lab README for the integration test.\n")
    (root / "manifest.csv").write_text("path,size_bytes,category\nREADME.md,1,metadata\n")
    (root / "qc_sessions.csv").write_text(f"idx,session\n0,{folder}\n")
    (root / "qc_views.csv").write_text(
        f"idx,session,camera,video_nb_frames\n0,{folder},back,{FRAMES}\n1,{folder},side,{FRAMES}\n"
    )
    (root / "mouse_skeleton.toml").write_text(SKELETON_TOML)
    model = root / "models" / "sleap-legacy" / "221106_013736.centroid.n_9068"
    model.mkdir(parents=True)
    (model / "training_config.json").write_text('{"model": "mock"}\n')


def build_example_raw() -> None:
    if EXAMPLE_RAW.exists():
        shutil.rmtree(EXAMPLE_RAW)
    raw = EXAMPLE_RAW / "sourcedata" / "raw"
    build_dyad(raw / "luc3d" / "MouseDyad-10M")
    build_slap(raw / "luc3d" / "SLAP-2M")
    (raw / ".transfer").mkdir()
    (raw / ".transfer" / "transfer-mock.json").write_text('{"schemaVersion": "1.0.0"}\n')


def build_expected_output() -> None:
    if EXPECTED_OUTPUT.exists():
        shutil.rmtree(EXPECTED_OUTPUT)
    for dataset in DATASETS:
        conv.convert_dataset(
            incoming_dir=EXAMPLE_RAW,
            standardized_dir=EXPECTED_OUTPUT / dataset,
            config_path=CONFIG,
            dataset_key=dataset,
            ffprobe_bin=str(SHIM),
        )


if __name__ == "__main__":
    build_example_raw()
    build_expected_output()
    print(f"\nFixtures written:\n  {EXAMPLE_RAW}\n  {EXPECTED_OUTPUT}")
