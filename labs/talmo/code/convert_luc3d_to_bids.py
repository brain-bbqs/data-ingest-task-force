#!/usr/bin/env python3
"""Convert a Talmo lab LUC3D collection into a BIDS study dataset.

One invocation converts one dataset of ``config.yaml`` (``mouse-dyad-10m`` or ``slap-2m``), reading
its collection under ``--input`` and writing the study under ``--output``::

    <output>/                       DatasetType "study"
      dataset_description.json
      README
      sourcedata/                   the lab's own documents, verbatim
      rawbids/                      DatasetType "raw", BEP047 videos with JSON sidecars
      derivatives/sleap/            2D pose, native SLEAP files, plus the models that made them
      derivatives/triangulation/    3D pose, reprojections and camera calibration, native files

Videos and pose files are copied byte-for-byte under BIDS names. Nothing is re-encoded.

A session whose ``scans.tsv`` already exists is skipped unless ``--overwrite`` is given. Dispatch appends
it when this file or the config changes. Sessions convert in parallel, one worker per CPU unless ``--jobs``
caps it. With ``--results`` the sessions left unconverted are written as
``{"pending": {name: reason}, "failed": {name: reason}}``, keyed by session folder name.

Example CLI usage (from the repository root)
--------------------------------------------
python3 labs/talmo/code/convert_luc3d_to_bids.py \\
    --input ember-incoming/000641 --output ember-standardized/000643 \\
    --config labs/talmo/code/config.yaml --dataset mouse-dyad-10m
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from fractions import Fraction
from pathlib import Path
from typing import Any

import h5py
import tomllib
import tqdm
import yaml

__version__ = "0.1.0"

RAW_DATASET = "rawbids"
SLEAP_DATASET = "derivatives/sleap"
TRIANGULATION_DATASET = "derivatives/triangulation"
DOCUMENTS_DIRECTORY = "sourcedata"
RAW_LINK_NAME = "rawbids"

# Largest array whose values are written into a sidecar. Node and track names fit, pose data does not.
MAX_INLINE_ELEMENTS = 64

H264_PROFILE_IDC = {
    "Constrained Baseline": "4240",
    "Baseline": "4200",
    "Main": "4d00",
    "Extended": "5800",
    "High": "6400",
    "High 10": "6e00",
    "High 4:2:2": "7a00",
    "High 4:4:4 Predictive": "f400",
}


class SourceDataError(Exception):
    """The source files of a session do not have the expected shape."""


class PendingSession(Exception):
    """A session cannot convert yet because an input it needs is not in the deposit."""


@dataclasses.dataclass
class Context:
    """Everything a session conversion needs besides the session itself."""

    settings: dict[str, Any]
    dataset: dict[str, Any]
    collection_dir: Path
    output_dir: Path
    ffprobe_bin: str
    link: str
    overwrite: bool
    skeleton: dict[str, Any]
    session_sheet: dict[str, dict[str, str]]
    quality_frames: dict[tuple[str, str], int]


@dataclasses.dataclass
class SessionOutcome:
    """What one session produced, for the dataset-level tables and the run report."""

    session_id: str
    status: str
    reason: str = ""
    subject: str = ""
    session_row: dict[str, Any] = dataclasses.field(default_factory=dict)
    participant_row: dict[str, Any] = dataclasses.field(default_factory=dict)
    ignored: list[str] = dataclasses.field(default_factory=list)
    warnings: list[str] = dataclasses.field(default_factory=list)


# ---------------------------------------------------------------------------
# Identity rules. Each naming decision lives in exactly one function.
# ---------------------------------------------------------------------------


def sanitize_label(text: str, /) -> str:
    """Reduce text to the alphanumeric characters BIDS and DANDI labels allow."""
    label = re.sub(r"[^0-9A-Za-z]", "", text)
    return label


def dyad_session_label(folder_name: str, /) -> str:
    """``20250827_141755`` becomes ``20250827141755``."""
    match = re.fullmatch(r"(\d{8})_(\d{6})", folder_name)
    if match is None:
        raise SourceDataError(f"Session folder {folder_name!r} is not named YYYYMMDD_HHMMSS")
    label = match.group(1) + match.group(2)
    return label


def slap_session_label(folder_name: str, /) -> str:
    """``10072022120554`` (MMDDYYYYHHMMSS) becomes ``20221007120554``."""
    match = re.fullmatch(r"(\d{2})(\d{2})(\d{4})(\d{6})", folder_name)
    if match is None:
        raise SourceDataError(f"Session folder {folder_name!r} is not named MMDDYYYYHHMMSS")
    month, day, year, time = match.groups()
    label = year + month + day + time
    return label


def iso_from_label(label: str, /) -> str:
    """``20250827141804`` becomes ``2025-08-27T14:18:04``. The source carries no timezone."""
    iso = f"{label[0:4]}-{label[4:6]}-{label[6:8]}T{label[8:10]}:{label[10:12]}:{label[12:14]}"
    return iso


def split_track_name(track_name: str, /) -> tuple[str, str]:
    """``181321_0`` is ``<animal ID>_<number of tail marks>`` per the dataset card."""
    match = re.fullmatch(r"(\d+)_(\d+)", track_name)
    if match is None:
        raise SourceDataError(f"Track name {track_name!r} is not <animal ID>_<tail marks>")
    parts = (match.group(1), match.group(2))
    return parts


def dyad_subject_label(animal_ids: list[str], /) -> str:
    """One subject per unique pair of animals, whatever order they were tracked in."""
    label = "x".join(sorted(sanitize_label(animal_id) for animal_id in animal_ids))
    return label


def recording_label(camera: str, /) -> str:
    """The camera folder name, a serial number (MouseDyad-10M) or a position (SLAP-2M)."""
    label = sanitize_label(camera)
    return label


# ---------------------------------------------------------------------------
# Small file helpers
# ---------------------------------------------------------------------------


def write_json(*, path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_tsv(*, path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow(["n/a" if row.get(column) in (None, "") else row[column] for column in columns])


def read_tsv(path: Path, /) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    return rows


def merge_tsv(*, path: Path, key: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
    """Add or replace rows by key, keeping rows written by earlier runs."""
    merged = {row[key]: row for row in read_tsv(path)}
    for row in rows:
        merged[row[key]] = row
    ordered = [merged[name] for name in sorted(merged)]
    write_tsv(path=path, columns=columns, rows=ordered)


def place_file(*, source: Path, destination: Path, link: str, overwrite: bool) -> None:
    """Copy or link one file to its output name without changing its bytes."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        if not overwrite and destination.stat().st_size == source.stat().st_size:
            return
        destination.unlink()
    if link == "hardlink":
        os.link(source, destination)
    elif link == "symlink":
        destination.symlink_to(source.resolve())
    else:
        shutil.copyfile(source, destination)


def relative_source(*, path: Path, ctx: Context) -> str:
    relative = path.relative_to(ctx.collection_dir).as_posix()
    return relative


# ---------------------------------------------------------------------------
# Video metadata
# ---------------------------------------------------------------------------


def run_ffprobe(*, path: Path, ffprobe_bin: str) -> dict[str, Any]:
    command = [ffprobe_bin, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    if ffprobe_bin.endswith(".py"):
        command = [sys.executable, *command]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise SourceDataError(f"ffprobe failed on {path.name}: {completed.stderr.strip()}")
    probe = json.loads(completed.stdout)
    return probe


def rfc6381_h264(stream: dict[str, Any], /) -> str | None:
    profile = H264_PROFILE_IDC.get(str(stream.get("profile", "")))
    level = stream.get("level")
    if profile is None or not isinstance(level, int) or level <= 0:
        return None
    codec = f"avc1.{profile}{level:02x}"
    return codec


def pixel_bit_depth(pixel_format: str, /) -> int:
    match = re.search(r"p(\d+)(le|be)$", pixel_format)
    depth = int(match.group(1)) if match else 8
    return depth


def build_video_sidecar(*, probe: dict[str, Any], path: Path) -> dict[str, Any]:
    """The BEP047 media fields, in the order the proposal lists them."""
    streams = [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "video"]
    if len(streams) != 1:
        raise SourceDataError(f"{path.name} has {len(streams)} video streams, expected 1")
    stream = streams[0]
    if any(other.get("codec_type") == "audio" for other in probe.get("streams", [])):
        raise SourceDataError(f"{path.name} has an audio stream, which the mapping does not cover")

    duration = stream.get("duration") or probe.get("format", {}).get("duration")
    rate_text = str(stream.get("avg_frame_rate") or "0/1")
    rate = Fraction(rate_text) if not rate_text.endswith("/0") else Fraction(0)
    sidecar: dict[str, Any] = {}
    if duration is not None:
        sidecar["RecordingDuration"] = round(float(duration), 6)
    sidecar["StartTime"] = 0
    sidecar["VideoCodec"] = stream.get("codec_name")
    if stream.get("codec_name") == "h264" and rfc6381_h264(stream):
        sidecar["VideoCodecRFC6381"] = rfc6381_h264(stream)
    if rate:
        sidecar["VideoFrameRate"] = round(float(rate), 6)
    if stream.get("nb_frames"):
        sidecar["VideoFrameCount"] = int(stream["nb_frames"])
    sidecar["ImageWidth"] = stream.get("width")
    sidecar["ImageHeight"] = stream.get("height")
    if stream.get("pix_fmt"):
        sidecar["ImagePixelFormat"] = stream["pix_fmt"]
        sidecar["ImageBitDepth"] = pixel_bit_depth(stream["pix_fmt"])
    return sidecar


def camera_calibration_block(*, calibration_path: Path, camera: str, ctx: Context) -> dict[str, Any]:
    """The ``[cam_N]`` table of an anipose calibration whose ``name`` is this camera."""
    calibration = tomllib.loads(calibration_path.read_text())
    blocks = [table for table in calibration.values() if isinstance(table, dict) and table.get("name") == camera]
    if len(blocks) != 1:
        names = sorted(str(table.get("name")) for table in calibration.values() if isinstance(table, dict))
        raise SourceDataError(f"Camera {camera!r} is not in {calibration_path.name}, which lists {names}")
    block = {
        "Description": (
            "This camera's block of the anipose/sleap-anipose calibration, preserved verbatim. "
            "Not part of the BIDS specification."
        ),
        "SourceFile": relative_source(path=calibration_path, ctx=ctx),
        "Parameters": blocks[0],
    }
    return block


# ---------------------------------------------------------------------------
# Pose file metadata
# ---------------------------------------------------------------------------


def _plain(value: Any, /) -> Any:
    """Turn an HDF5 value into something JSON can hold."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "tolist"):
        return _plain(value.tolist())
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _maybe_json(text: Any, /) -> Any:
    if isinstance(text, str) and text[:1] in "{[":
        try:
            return json.loads(text)
        except ValueError:
            return text
    return text


def summarize_hdf5(path: Path, /) -> dict[str, Any]:
    """Every dataset's shape and type, plus the values of the small ones (names, rates, provenance)."""
    datasets: dict[str, Any] = {}

    def visit(name: str, node: Any) -> None:
        if not isinstance(node, h5py.Dataset):
            return
        entry: dict[str, Any] = {"Shape": list(node.shape), "DataType": str(node.dtype)}
        for attribute, value in node.attrs.items():
            if attribute != "json":
                entry[attribute] = _plain(value)
        is_text = node.dtype.kind in "SOU"
        if node.dtype.names is None and node.size <= MAX_INLINE_ELEMENTS and (is_text or node.size <= 2):
            entry["Value"] = _maybe_json(_plain(node[()]))
        datasets[name] = entry

    with h5py.File(path, "r") as file:
        file.visititems(visit)
    return datasets


def summarize_slp(path: Path, /) -> dict[str, Any]:
    """What a SLEAP labels file says about itself, without loading its points."""
    with h5py.File(path, "r") as file:
        metadata = json.loads(_plain(file["metadata"].attrs["json"]))
        videos = [json.loads(_plain(entry)) for entry in file["videos_json"][()]]
        tracks = [json.loads(_plain(entry)) for entry in file["tracks_json"][()]] if "tracks_json" in file else []
        summary = {
            "FormatVersion": metadata.get("version"),
            "LabeledFrameCount": int(file["frames"].shape[0]),
            "InstanceCount": int(file["instances"].shape[0]),
            "TrackNames": [track[1] for track in tracks],
            "Videos": [video.get("filename") or video.get("backend", {}).get("filename") for video in videos],
            "Provenance": metadata.get("provenance") or {},
        }
    return summary


def describe_file(path: Path, /) -> dict[str, Any]:
    if path.name.endswith(".slp"):
        description = {"Format": "SLEAP labels (HDF5)", **summarize_slp(path)}
    elif path.name.endswith(".h5"):
        description = {"Format": "HDF5", "Datasets": summarize_hdf5(path)}
    elif path.name.endswith(".toml"):
        description = {"Format": "TOML"}
    else:
        description = {}
    return description


def load_skeleton(path: Path, /) -> dict[str, Any]:
    if not path.is_file():
        return {}
    skeleton_toml = tomllib.loads(path.read_text())
    skeleton = {"NodeNames": skeleton_toml.get("nodes", []), "Edges": skeleton_toml.get("edges", [])}
    return skeleton


# ---------------------------------------------------------------------------
# Emitting output files
# ---------------------------------------------------------------------------


def session_stem(*, subject: str, session: str) -> str:
    stem = f"sub-{subject}_ses-{session}"
    return stem


def beh_directory(*, ctx: Context, dataset: str, subject: str, session: str) -> Path:
    directory = ctx.output_dir / dataset / f"sub-{subject}" / f"ses-{session}" / "beh"
    return directory


def emit_video(
    *,
    ctx: Context,
    source: Path,
    subject: str,
    session: str,
    camera: str,
    extra: dict[str, Any],
    outcome: SessionOutcome,
) -> tuple[str, dict[str, Any]]:
    """Place one camera's video in the raw dataset with its sidecar. Returns its name and sidecar."""
    stem = f"{session_stem(subject=subject, session=session)}_recording-{recording_label(camera)}_video"
    directory = beh_directory(ctx=ctx, dataset=RAW_DATASET, subject=subject, session=session)
    probe = run_ffprobe(path=source, ffprobe_bin=ctx.ffprobe_bin)
    sidecar = build_video_sidecar(probe=probe, path=source)
    sidecar.update(extra)
    sidecar["SourceFile"] = relative_source(path=source, ctx=ctx)

    expected_frames = ctx.quality_frames.get((outcome.session_id, camera))
    if expected_frames is not None and sidecar.get("VideoFrameCount") != expected_frames:
        outcome.warnings.append(
            f"{source.name}: {sidecar.get('VideoFrameCount')} frames, the lab's qc_views.csv says {expected_frames}"
        )

    place_file(source=source, destination=directory / f"{stem}.mp4", link=ctx.link, overwrite=ctx.overwrite)
    write_json(path=directory / f"{stem}.json", data=sidecar)
    return f"{stem}.mp4", sidecar


def emit_derivative(
    *,
    ctx: Context,
    dataset: str,
    subject: str,
    session: str,
    entities: str,
    suffix: str,
    sources: list[Path],
    description: str,
    videos: list[str],
    extra: dict[str, Any],
) -> None:
    """Place the native files of one derivative under a shared BIDS stem, with one sidecar for them."""
    stem = f"{session_stem(subject=subject, session=session)}{entities}_{suffix}"
    directory = beh_directory(ctx=ctx, dataset=dataset, subject=subject, session=session)
    files: dict[str, Any] = {}
    for source in sources:
        extension = ".slp" if source.name.endswith(".slp") else source.suffix
        name = f"{stem}{extension}"
        if name in files:
            raise SourceDataError(f"Two source files map to {name}")
        place_file(source=source, destination=directory / name, link=ctx.link, overwrite=ctx.overwrite)
        files[name] = {"SourceFile": relative_source(path=source, ctx=ctx), **describe_file(source)}

    raw_prefix = f"bids:{RAW_LINK_NAME}:sub-{subject}/ses-{session}/beh/"
    sidecar = {"Description": description, "Sources": [raw_prefix + video for video in videos], **extra, "Files": files}
    write_json(path=directory / f"{stem}.json", data=sidecar)


def only_match(*, directory: Path, pattern: str, what: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise SourceDataError(f"{directory.name}: expected one {what} ({pattern}), found {len(matches)}")
    return matches[0]


def optional_match(*, directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern))
    if len(matches) > 1:
        raise SourceDataError(f"{directory.name}: more than one file matches {pattern}")
    match = matches[0] if matches else None
    return match


def write_scans(*, ctx: Context, subject: str, session: str, videos: list[str], acq_time: str) -> None:
    stem = session_stem(subject=subject, session=session)
    directory = ctx.output_dir / RAW_DATASET / f"sub-{subject}" / f"ses-{session}"
    rows = [{"filename": f"ses-{session}/beh/{video}", "acq_time": acq_time} for video in sorted(videos)]
    write_json(
        path=directory / f"{stem}_scans.json",
        data={
            "filename": {"Description": "Path to the video, relative to the subject directory."},
            "acq_time": {
                "Description": (
                    "Start of acquisition, from the timestamp in the source names. Local time of the "
                    "acquisition computer. The source carries no timezone."
                )
            },
        },
    )
    # Written last. Its presence marks the session as converted.
    write_tsv(path=directory / f"{stem}_scans.tsv", columns=["filename", "acq_time"], rows=rows)


def scans_path(*, ctx: Context, subject: str, session: str) -> Path:
    stem = session_stem(subject=subject, session=session)
    path = ctx.output_dir / RAW_DATASET / f"sub-{subject}" / f"ses-{session}" / f"{stem}_scans.tsv"
    return path


def report_leftovers(*, session_dir: Path, handled: set[Path], outcome: SessionOutcome, ctx: Context) -> None:
    for path in sorted(session_dir.rglob("*")):
        if path.is_file() and path not in handled:
            outcome.ignored.append(relative_source(path=path, ctx=ctx))


# ---------------------------------------------------------------------------
# MouseDyad-10M
# ---------------------------------------------------------------------------

DYAD_SESSION_COLUMNS = [
    "session_id",
    "acq_time",
    "source_session",
    "male_id",
    "female_id",
    "male_track_name",
    "female_track_name",
    "experimental_code",
    "frame_rate",
    "pose3d_frame_count",
    "calibration",
    "notes",
]
DYAD_PARTICIPANT_COLUMNS = ["participant_id", "species", "strain", "sex", "male_id", "female_id"]


def read_dyad_roster(path: Path, /) -> dict[str, Any]:
    with h5py.File(path, "r") as file:
        roster = {
            "track_names": [_plain(name) for name in file["track_names"][()]],
            "experimental_code": _plain(file["experimental_code"][()]) if "experimental_code" in file else None,
            "frame_rate": float(file["recording_frame_rate"][()]) if "recording_frame_rate" in file else None,
            "frame_count": int(file["tracks"].shape[0]),
        }
    return roster


def convert_dyad_session(*, session_dir: Path, ctx: Context) -> SessionOutcome:
    outcome = SessionOutcome(session_id=session_dir.name, status="converted")
    session = dyad_session_label(session_dir.name)

    pose3d = optional_match(directory=session_dir, pattern="*_points3d_translated_rotated_metric.h5")
    if pose3d is None:
        raise PendingSession("No 3D pose file, which is the only source of the animal pair")
    roster = read_dyad_roster(pose3d)
    if len(roster["track_names"]) != 2:
        raise SourceDataError(f"3D file names {len(roster['track_names'])} tracks, expected 2")
    animals = [split_track_name(name)[0] for name in roster["track_names"]]
    subject = dyad_subject_label(animals)
    outcome.subject = subject
    sexes = ctx.dataset["track_sexes"]
    by_sex = dict(zip(sexes, zip(animals, roster["track_names"], strict=True), strict=True))

    if scans_path(ctx=ctx, subject=subject, session=session).exists() and not ctx.overwrite:
        outcome.status = "skipped"
        return outcome

    handled = {pose3d}
    calibration_dir = session_dir / "calibration"
    calibration = only_match(directory=calibration_dir, pattern="*_calibration.toml", what="calibration")
    board = optional_match(directory=calibration_dir, pattern="*_cboard.toml")
    detections = optional_match(directory=calibration_dir, pattern="*_calibration.metadata.h5")
    for name, path in (("ChArUco board file", board), ("calibration detections file", detections)):
        if path is None:
            outcome.warnings.append(f"No {name}")

    cameras = sorted(path.name for path in session_dir.iterdir() if path.is_dir() and path.name != "calibration")
    if not cameras:
        raise SourceDataError("No camera folders")

    videos: dict[str, str] = {}
    timestamps = set()
    pose_frame_rate = roster["frame_rate"]
    skeleton = {"Skeleton": ctx.skeleton} if ctx.skeleton else {}
    for camera in cameras:
        camera_dir = session_dir / camera
        video = only_match(directory=camera_dir, pattern="*.mp4", what="video")
        timestamp = video.stem.split("-")[-1]
        timestamps.add(timestamp)
        extra = {
            "DeviceSerialNumber": camera,
            "Synchronization": {"Description": ctx.dataset["synchronization"], "SourceTimestamp": timestamp},
            "CameraCalibration": camera_calibration_block(calibration_path=calibration, camera=camera, ctx=ctx),
        }
        videos[camera], video_sidecar = emit_video(
            ctx=ctx, source=video, subject=subject, session=session, camera=camera, extra=extra, outcome=outcome
        )
        handled.add(video)

        tracks = [
            path
            for path in (
                optional_match(directory=camera_dir, pattern="*.slp"),
                optional_match(directory=camera_dir, pattern="*.analysis.h5"),
            )
            if path is not None
        ]
        if not tracks:
            outcome.warnings.append(f"Camera {camera} has no 2D pose files")
            continue
        handled.update(tracks)
        emit_derivative(
            ctx=ctx,
            dataset=SLEAP_DATASET,
            subject=subject,
            session=session,
            entities=f"_recording-{recording_label(camera)}_desc-predictions",
            suffix="pose",
            sources=tracks,
            description=ctx.dataset["pose_2d_description"],
            videos=[videos[camera]],
            extra={"Units": "pixel", "SamplingFrequency": video_sidecar.get("VideoFrameRate"), **skeleton},
        )

    if len(timestamps) != 1:
        raise SourceDataError(f"Cameras disagree on the recording timestamp: {sorted(timestamps)}")
    acq_time = iso_from_label(timestamps.pop())
    all_videos = [videos[camera] for camera in cameras]

    emit_derivative(
        ctx=ctx,
        dataset=TRIANGULATION_DATASET,
        subject=subject,
        session=session,
        entities="_desc-arena",
        suffix="pose",
        sources=[pose3d],
        description=(
            "3D pose, translated and rotated into the arena frame with z as height and the floor at z = 0. "
            "Axes of `tracks` are (frame, animal, node, xyz)."
        ),
        videos=all_videos,
        extra={
            "Units": ctx.dataset["pose_units_3d"],
            "SamplingFrequency": pose_frame_rate,
            "TrackNames": roster["track_names"],
            "TrackSexes": sexes,
            **skeleton,
        },
    )
    emit_derivative(
        ctx=ctx,
        dataset=TRIANGULATION_DATASET,
        subject=subject,
        session=session,
        entities="",
        suffix="calibration",
        sources=[calibration],
        description="Camera intrinsics, distortion and extrinsics in anipose/sleap-anipose format.",
        videos=all_videos,
        extra={},
    )
    handled.add(calibration)
    if board is not None:
        emit_derivative(
            ctx=ctx,
            dataset=TRIANGULATION_DATASET,
            subject=subject,
            session=session,
            entities="_desc-board",
            suffix="calibration",
            sources=[board],
            description="The ChArUco board used for the calibration.",
            videos=[],
            extra={},
        )
        handled.add(board)
    if detections is not None:
        emit_derivative(
            ctx=ctx,
            dataset=TRIANGULATION_DATASET,
            subject=subject,
            session=session,
            entities="_desc-detections",
            suffix="calibration",
            sources=[detections],
            description="Board corners detected, triangulated and reprojected during the calibration.",
            videos=[],
            extra={},
        )
        handled.add(detections)

    outcome.session_row = {
        "session_id": f"ses-{session}",
        "acq_time": acq_time,
        "source_session": session_dir.name,
        "male_id": by_sex.get("M", ("", ""))[0],
        "female_id": by_sex.get("F", ("", ""))[0],
        "male_track_name": by_sex.get("M", ("", ""))[1],
        "female_track_name": by_sex.get("F", ("", ""))[1],
        "experimental_code": roster["experimental_code"],
        "frame_rate": roster["frame_rate"],
        "pose3d_frame_count": roster["frame_count"],
        "calibration": calibration.name,
        "notes": ctx.dataset.get("session_notes", {}).get(session_dir.name, ""),
    }
    outcome.participant_row = {
        "participant_id": f"sub-{subject}",
        "species": ctx.settings["species"],
        "strain": ctx.dataset["strain"],
        "sex": "n/a",
        "male_id": by_sex.get("M", ("", ""))[0],
        "female_id": by_sex.get("F", ("", ""))[0],
    }
    report_leftovers(session_dir=session_dir, handled=handled, outcome=outcome, ctx=ctx)
    write_scans(ctx=ctx, subject=subject, session=session, videos=all_videos, acq_time=acq_time)
    return outcome


# ---------------------------------------------------------------------------
# SLAP-2M
# ---------------------------------------------------------------------------

SLAP_SUBJECT = "multi"
SLAP_SHEET_COLUMNS = [
    "animals",
    "white_mice",
    "agouti_mice",
    "black_mice",
    "obstacle_rating",
    "bedding",
    "difficulty",
    "frames",
    "duration",
]
SLAP_SESSION_COLUMNS = ["session_id", "acq_time", "source_session", *SLAP_SHEET_COLUMNS, "notes"]
SLAP_PARTICIPANT_COLUMNS = ["participant_id", "species", "strain", "sex"]

# (glob inside a camera folder, derivative dataset, desc label, description)
SLAP_CAMERA_PRODUCTS = [
    (
        ["*.predictions.proofread.slp", "*.predictions.proofread.slp.analysis.h5"],
        SLEAP_DATASET,
        "proofread",
        "Proofread 2D SLEAP tracks of this camera.",
    ),
    (
        ["*.mp4.predictions.slp"],
        SLEAP_DATASET,
        "predictions",
        "2D predictions of this camera, not proofread. For side and sideL they come from a separate side-camera model.",
    ),
    (
        ["*.reprojections.slp", "*.reprojections.slp.h5"],
        TRIANGULATION_DATASET,
        "reprojections",
        "The 3D pose reprojected into this camera, as SLEAP labels.",
    ),
]

# (file name, desc label, suffix, description, carries pose units)
SLAP_SESSION_PRODUCTS = [
    ("points3d.h5", "camera", "pose", "3D pose in the calibration (camera) frame.", True),
    ("aligned_points3d.h5", "arena", "pose", "3D pose aligned to the arena.", True),
    ("aligned_cage_points3d.h5", "arenalandmarks", "pose", "The arena landmarks in the aligned frame.", True),
    ("reprojections.h5", "reprojections", "pose", "The 3D pose reprojected into every camera, in pixels.", False),
    ("calibration.toml", "", "calibration", "Camera intrinsics, distortion and extrinsics in anipose format.", False),
    ("alignment.toml", "arena", "calibration", "The transform from the calibration frame to the arena.", False),
]


def convert_slap_session(*, session_dir: Path, ctx: Context) -> SessionOutcome:
    outcome = SessionOutcome(session_id=session_dir.name, status="converted", subject=SLAP_SUBJECT)
    session = slap_session_label(session_dir.name)
    subject = SLAP_SUBJECT
    if scans_path(ctx=ctx, subject=subject, session=session).exists() and not ctx.overwrite:
        outcome.status = "skipped"
        return outcome

    calibration = only_match(directory=session_dir, pattern="calibration.toml", what="calibration")
    cameras = sorted(path.name for path in session_dir.iterdir() if path.is_dir())
    if not cameras:
        raise SourceDataError("No camera folders")

    handled: set[Path] = set()
    videos: dict[str, str] = {}
    skeleton = {"Skeleton": ctx.skeleton} if ctx.skeleton else {}
    frame_rate = None
    for camera in cameras:
        camera_dir = session_dir / camera
        video = only_match(directory=camera_dir, pattern="*_h264_CRF20_denoised.mp4", what="video")
        match = re.match(rf"{re.escape(camera)}-(\d{{14}})-", video.name)
        timestamp = slap_session_label(match.group(1)) if match else None
        extra = {
            "DevicePosition": camera,
            "Synchronization": {"Description": ctx.dataset["synchronization"], "SourceTimestamp": timestamp},
            "CameraCalibration": camera_calibration_block(calibration_path=calibration, camera=camera, ctx=ctx),
            "SourceEncoding": ctx.dataset["source_encoding"],
        }
        videos[camera], video_sidecar = emit_video(
            ctx=ctx, source=video, subject=subject, session=session, camera=camera, extra=extra, outcome=outcome
        )
        frame_rate = video_sidecar.get("VideoFrameRate")
        handled.add(video)

        for patterns, dataset, label, description in SLAP_CAMERA_PRODUCTS:
            sources = [
                path
                for pattern in patterns
                if (path := optional_match(directory=camera_dir, pattern=pattern)) is not None
            ]
            if not sources:
                continue
            handled.update(sources)
            emit_derivative(
                ctx=ctx,
                dataset=dataset,
                subject=subject,
                session=session,
                entities=f"_recording-{recording_label(camera)}_desc-{label}",
                suffix="pose",
                sources=sources,
                description=description,
                videos=[videos[camera]],
                extra={"Units": "pixel", "SamplingFrequency": frame_rate, **skeleton},
            )

    all_videos = [videos[camera] for camera in cameras]
    for name, label, suffix, description, has_units in SLAP_SESSION_PRODUCTS:
        source = session_dir / name
        if not source.is_file():
            outcome.warnings.append(f"No {name}")
            continue
        handled.add(source)
        extra: dict[str, Any] = {}
        if suffix == "pose":
            extra = {"Units": ctx.dataset["pose_units_3d"] if has_units else "pixel", "SamplingFrequency": frame_rate}
            if label != "arenalandmarks":
                extra.update(skeleton)
        emit_derivative(
            ctx=ctx,
            dataset=TRIANGULATION_DATASET,
            subject=subject,
            session=session,
            entities=f"_desc-{label}" if label else "",
            suffix=suffix,
            sources=[source],
            description=description,
            videos=all_videos,
            extra=extra,
        )

    sheet_row = ctx.session_sheet.get(session_dir.name)
    if sheet_row is None:
        outcome.warnings.append("Session is not in the master sheet, so its animal counts are unknown")
        sheet_row = {}
    acq_time = iso_from_label(session)
    outcome.session_row = {
        "session_id": f"ses-{session}",
        "acq_time": acq_time,
        "source_session": session_dir.name,
        **{column: sheet_row.get(column, "") for column in SLAP_SHEET_COLUMNS},
        "notes": ctx.dataset.get("session_notes", {}).get(session_dir.name, ""),
    }
    outcome.participant_row = {
        "participant_id": f"sub-{subject}",
        "species": ctx.settings["species"],
        "strain": ctx.dataset["strain"],
        "sex": "n/a",
    }
    report_leftovers(session_dir=session_dir, handled=handled, outcome=outcome, ctx=ctx)
    write_scans(ctx=ctx, subject=subject, session=session, videos=all_videos, acq_time=acq_time)
    return outcome


# ---------------------------------------------------------------------------
# Layout registry
# ---------------------------------------------------------------------------

LAYOUTS = {
    "mouse-dyad": {
        "session_glob": "sessions/*",
        "convert": convert_dyad_session,
        "session_columns": DYAD_SESSION_COLUMNS,
        "participant_columns": DYAD_PARTICIPANT_COLUMNS,
    },
    "slap": {
        "session_glob": "sessions/*/*",
        "convert": convert_slap_session,
        "session_columns": SLAP_SESSION_COLUMNS,
        "participant_columns": SLAP_PARTICIPANT_COLUMNS,
    },
}

COLUMN_DESCRIPTIONS = {
    "participant_id": "One row per subject directory.",
    "species": "Binomial species name.",
    "strain": "Mouse strain or strains, from the lab's dataset card.",
    "sex": "n/a, since a subject here is more than one animal.",
    "male_id": "Animal ID of the male of the pair.",
    "female_id": "Animal ID of the female of the pair.",
    "male_track_name": "The male's track name in the 3D file, <animal ID>_<number of tail marks>.",
    "female_track_name": "The female's track name in the 3D file, <animal ID>_<number of tail marks>.",
    "session_id": "Session label.",
    "acq_time": "Start of acquisition, local time of the acquisition computer. The source carries no timezone.",
    "source_session": "Name of the session folder in the lab's deposit.",
    "experimental_code": "The lab's code for the session, verbatim. Its meaning is not documented.",
    "frame_rate": "Recording frame rate stored in the 3D file, in Hz.",
    "pose3d_frame_count": "Frames in the 3D file. It can be a few frames shorter than the videos.",
    "calibration": "Name of the calibration file the session uses.",
    "notes": "Known issues with the session, from the lab README and dataset card.",
    "animals": "Number of mice in the arena, from the lab's master sheet.",
    "white_mice": "Number of white mice, from the lab's master sheet.",
    "agouti_mice": "Number of agouti mice, from the lab's master sheet.",
    "black_mice": "Number of black mice, from the lab's master sheet.",
    "obstacle_rating": "The lab's rating of the enrichment objects in the arena, verbatim from the master sheet.",
    "bedding": "Bedding color, from the lab's master sheet.",
    "difficulty": "The lab's difficulty rating, from the number of animals and the enrichment objects.",
    "frames": "Frames per camera, from the lab's master sheet.",
    "duration": "Duration as the lab's master sheet gives it, in minutes. Blank for six sessions.",
}


def column_sidecar(columns: list[str], /) -> dict[str, Any]:
    sidecar = {column: {"Description": COLUMN_DESCRIPTIONS[column]} for column in columns}
    return sidecar


# ---------------------------------------------------------------------------
# Dataset-level files
# ---------------------------------------------------------------------------


def readme_text(*, title: str, ctx: Context, body: list[str]) -> str:
    lines = [title, "", ctx.dataset["description"], "", *body]
    issues = ctx.dataset.get("known_issues", [])
    if issues:
        lines += ["", "Known issues", ""] + [f"- {issue}" for issue in issues]
    text = "\n".join(lines) + "\n"
    return text


def write_dataset_files(*, ctx: Context) -> None:
    settings, dataset, output = ctx.settings, ctx.dataset, ctx.output_dir
    name = dataset["name"]
    generator = {
        "Name": "convert_luc3d_to_bids.py",
        "Version": __version__,
        "CodeURL": "https://github.com/brain-bbqs/data-ingest-task-force/tree/main/labs/talmo",
    }
    common = {
        "BIDSVersion": settings["bids_version"],
        "License": settings["license"],
        "Authors": settings["authors"],
        "Funding": settings["funding"],
        "ReferencesAndLinks": settings["references"],
    }

    write_json(
        path=output / "dataset_description.json",
        data={"Name": name, "DatasetType": "study", **common, "GeneratedBy": [generator]},
    )
    (output / "README").write_text(
        readme_text(
            title=f"{name} (BIDS study dataset)",
            ctx=ctx,
            body=[
                "Layout",
                "",
                "- sourcedata/ holds the lab's own documents, verbatim.",
                "- rawbids/ holds the videos as a BEP047 raw BIDS dataset.",
                "- derivatives/sleap/ holds the 2D pose and the models that made it.",
                "- derivatives/triangulation/ holds the 3D pose, reprojections and camera calibration.",
                "",
                f"Institution: {dataset['institution']}",
            ],
        )
    )

    raw = output / RAW_DATASET
    write_json(
        path=raw / "dataset_description.json",
        data={
            "Name": f"{name} videos",
            "DatasetType": "raw",
            **common,
            "ReferencesAndLinks": [*settings["references"], settings["bep047_reference"]],
            "GeneratedBy": [
                {**generator, "Description": "Places the videos under BEP047 names. Media metadata via ffprobe."}
            ],
        },
    )
    (raw / "README").write_text(
        readme_text(
            title=f"{name} videos",
            ctx=ctx,
            body=[
                "One video per camera per session, copied unmodified. The recording entity names the camera.",
                "Each sidecar adds the camera's calibration block and the source file name.",
                "The animals of each session are listed in the sessions.tsv of its subject.",
            ],
        )
    )

    for key, title, body in (
        (
            "sleap",
            "2D pose",
            "Per-camera 2D pose in native SLEAP .slp and analysis .h5 files. models/ holds the SLEAP models verbatim.",
        ),
        (
            "triangulation",
            "3D pose and calibration",
            "3D pose, reprojections and camera calibration in the lab's native HDF5 and TOML files.",
        ),
    ):
        root = output / "derivatives" / key
        write_json(
            path=root / "dataset_description.json",
            data={
                "Name": f"{name} {title}",
                "DatasetType": "derivative",
                **common,
                "GeneratedBy": [*dataset["generated_by"][key], generator],
                "SourceDatasets": [{"URL": f"../../{RAW_DATASET}/"}],
                "DatasetLinks": {RAW_LINK_NAME: f"../../{RAW_DATASET}"},
            },
        )
        (root / "README").write_text(
            readme_text(
                title=f"{name} {title}",
                ctx=ctx,
                body=[
                    body,
                    "Files keep their native formats and bytes. The pose and calibration suffixes are not part",
                    "of the BIDS specification. Each JSON sidecar describes the files that share its name.",
                ],
            )
        )


def copy_tree(*, source: Path, destination: Path, ctx: Context) -> int:
    count = 0
    for path in sorted(source.rglob("*")):
        if path.is_file():
            target = destination / path.relative_to(source)
            place_file(source=path, destination=target, link=ctx.link, overwrite=ctx.overwrite)
            count += 1
    return count


def copy_collection_files(*, ctx: Context) -> list[str]:
    """Documents and models. Returns the collection-level files no rule covers."""
    handled = {"sessions", "models"}
    for name in ctx.dataset["documents"]:
        source = ctx.collection_dir / name
        handled.add(name)
        if source.is_file():
            place_file(
                source=source,
                destination=ctx.output_dir / DOCUMENTS_DIRECTORY / name,
                link="copy",
                overwrite=ctx.overwrite,
            )
        else:
            print(f"  document not found: {name}")
    models = ctx.collection_dir / "models"
    if models.is_dir():
        count = copy_tree(source=models, destination=ctx.output_dir / SLEAP_DATASET / "models", ctx=ctx)
        print(f"  models: {count} files")
    ignored = sorted(path.name for path in ctx.collection_dir.iterdir() if path.name not in handled)
    return ignored


def write_tables(*, ctx: Context, outcomes: list[SessionOutcome]) -> None:
    layout = LAYOUTS[ctx.dataset["layout"]]
    raw = ctx.output_dir / RAW_DATASET
    converted = [outcome for outcome in outcomes if outcome.status == "converted"]

    participants = {outcome.participant_row["participant_id"]: outcome.participant_row for outcome in converted}
    if participants or not (raw / "participants.tsv").exists():
        merge_tsv(
            path=raw / "participants.tsv",
            key="participant_id",
            columns=layout["participant_columns"],
            rows=list(participants.values()),
        )
    write_json(path=raw / "participants.json", data=column_sidecar(layout["participant_columns"]))

    by_subject: dict[str, list[dict[str, Any]]] = {}
    for outcome in converted:
        by_subject.setdefault(outcome.subject, []).append(outcome.session_row)
    for subject, rows in by_subject.items():
        directory = raw / f"sub-{subject}"
        merge_tsv(
            path=directory / f"sub-{subject}_sessions.tsv",
            key="session_id",
            columns=layout["session_columns"],
            rows=rows,
        )
        write_json(
            path=directory / f"sub-{subject}_sessions.json",
            data=column_sidecar(layout["session_columns"]),
        )


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------


def resolve_worker_count(*, requested: int | None, task_count: int) -> int:
    available = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    workers = max(1, min(requested or available, task_count))
    return workers


def read_session_sheet(*, ctx_dataset: dict[str, Any], collection_dir: Path) -> dict[str, dict[str, str]]:
    name = ctx_dataset.get("session_sheet")
    if not name or not (collection_dir / name).is_file():
        return {}
    with (collection_dir / name).open(newline="") as stream:
        sheet = {row["session"]: row for row in csv.DictReader(stream, delimiter="\t")}
    return sheet


def read_quality_frames(collection_dir: Path, /) -> dict[tuple[str, str], int]:
    """Frame counts the lab measured per session and camera, to cross-check ours against."""
    path = collection_dir / "qc_views.csv"
    if not path.is_file():
        return {}
    frames = {}
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("video_nb_frames"):
                frames[(row["session"], row["camera"])] = int(float(row["video_nb_frames"]))
    return frames


def convert_one(*, session_dir: Path, ctx: Context) -> SessionOutcome:
    convert = LAYOUTS[ctx.dataset["layout"]]["convert"]
    try:
        outcome = convert(session_dir=session_dir, ctx=ctx)
    except PendingSession as error:
        outcome = SessionOutcome(session_id=session_dir.name, status="pending", reason=str(error))
    except Exception as error:  # noqa: BLE001 - one bad session must not stop the batch
        traceback.print_exc()
        outcome = SessionOutcome(
            session_id=session_dir.name, status="failed", reason=f"{type(error).__name__}: {error}"
        )
    return outcome


def convert_dataset(
    *,
    incoming_dir: Path,
    standardized_dir: Path,
    config_path: Path,
    dataset_key: str,
    overwrite: bool = False,
    jobs: int | None = None,
    link: str = "copy",
    ffprobe_bin: str = "ffprobe",
    results_path: Path | None = None,
) -> int:
    settings = yaml.safe_load(config_path.read_text())
    if dataset_key not in settings["datasets"]:
        raise SystemExit(f"Unknown dataset {dataset_key!r}. Choices: {sorted(settings['datasets'])}")
    dataset = settings["datasets"][dataset_key]
    layout = LAYOUTS[dataset["layout"]]
    collection_dir = incoming_dir / dataset["source"]

    session_dirs = sorted(path for path in collection_dir.glob(layout["session_glob"]) if path.is_dir())
    if not session_dirs:
        print(f"No sessions found under {collection_dir}. Nothing to do.")
        if results_path is not None:
            write_json(path=results_path, data={"pending": {}, "failed": {}})
        return 0

    ctx = Context(
        settings=settings,
        dataset=dataset,
        collection_dir=collection_dir,
        output_dir=standardized_dir,
        ffprobe_bin=ffprobe_bin,
        link=link,
        overwrite=overwrite,
        skeleton=load_skeleton(collection_dir / "mouse_skeleton.toml"),
        session_sheet=read_session_sheet(ctx_dataset=dataset, collection_dir=collection_dir),
        quality_frames=read_quality_frames(collection_dir),
    )
    standardized_dir.mkdir(parents=True, exist_ok=True)
    print(f"{dataset['name']}: {len(session_dirs)} sessions under {collection_dir}")
    write_dataset_files(ctx=ctx)
    ignored_top = copy_collection_files(ctx=ctx)

    workers = resolve_worker_count(requested=jobs, task_count=len(session_dirs))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(convert_one, session_dir=session_dir, ctx=ctx) for session_dir in session_dirs]
        progress = tqdm.tqdm(concurrent.futures.as_completed(futures), total=len(futures), unit="session")
        outcomes = [future.result() for future in progress]
    outcomes.sort(key=lambda outcome: outcome.session_id)
    write_tables(ctx=ctx, outcomes=outcomes)

    counts = {status: sum(outcome.status == status for outcome in outcomes) for status in STATUSES}
    print(", ".join(f"{count} {status}" for status, count in counts.items()))
    for outcome in outcomes:
        for warning in outcome.warnings:
            print(f"  warning [{outcome.session_id}] {warning}")
        if outcome.status in ("pending", "failed"):
            print(f"  {outcome.status} [{outcome.session_id}] {outcome.reason}")
    ignored = [f"{name} (collection level)" for name in ignored_top]
    ignored += [path for outcome in outcomes for path in outcome.ignored]
    if ignored:
        print(f"Ignored {len(ignored)} source files that no mapping rule covers:")
        for path in ignored:
            print(f"  {path}")

    pending = {outcome.session_id: outcome.reason for outcome in outcomes if outcome.status == "pending"}
    failed = {outcome.session_id: outcome.reason for outcome in outcomes if outcome.status == "failed"}
    if results_path is not None:
        write_json(path=results_path, data={"pending": pending, "failed": failed})
    exit_code = 1 if pending or failed else 0
    return exit_code


STATUSES = ("converted", "skipped", "pending", "failed")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--input", type=Path, required=True, help="Incoming dandiset directory")
    parser.add_argument("--output", type=Path, required=True, help="Standardized dandiset directory (the study root)")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.yaml"))
    parser.add_argument("--dataset", required=True, help="Dataset key in the config (mouse-dyad-10m or slap-2m)")
    parser.add_argument("--overwrite", action="store_true", help="Reconvert sessions that already have output")
    parser.add_argument("--jobs", type=int, default=None, help="Parallel sessions (default: one per CPU)")
    parser.add_argument("--link", choices=["copy", "hardlink", "symlink"], default="copy", help="How to place files")
    parser.add_argument("--ffprobe", default="ffprobe", help="Path to the ffprobe executable")
    parser.add_argument("--results", type=Path, default=None, help="Write the sessions left unconverted to this JSON")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None, /) -> int:
    args = build_arg_parser().parse_args(argv)
    exit_code = convert_dataset(
        incoming_dir=args.input,
        standardized_dir=args.output,
        config_path=args.config,
        dataset_key=args.dataset,
        overwrite=args.overwrite,
        jobs=args.jobs,
        link=args.link,
        ffprobe_bin=args.ffprobe,
        results_path=args.results,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
