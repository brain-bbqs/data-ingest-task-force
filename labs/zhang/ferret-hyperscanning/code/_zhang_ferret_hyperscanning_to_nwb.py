#!/usr/bin/env python3
"""Convert one Zhang-lab ferret hyperscanning recording into NWB files.

A recording is one SpikeGadgets ``.rec`` directory holding a Trodes file of
the same name, with the five behavior videos and five calibration videos of
that session in a sibling ``Videos/`` directory::

    Ferret_Hyperscanning/<pair>/<MM.DD.YYYY>/
      <A>HS<n>_<B>HS<m>_<YYYYMMDD>_<HHMMSS>.rec/
        <A>HS<n>_<B>HS<m>_<YYYYMMDD>_<HHMMSS>.rec
      Videos/
        cam<NN>-<MMDDYYYYHHMMSS>-0000.avi
        cam<NN>-cal-<MMDDYYYYHHMMSS>-0000.avi

The recording holds both animals' headstages. It becomes two NWB files, one
per animal, in the DANDI layout, with the shared videos placed next to the
lower-numbered animal's file and referenced from both::

    <output>/
      sub-<A>/
        sub-<A>_ses-<label>_behavior+ecephys.nwb
        sub-<A>_ses-<label>_cam<NN>_video.avi
        sub-<A>_ses-<label>_cam<NN>_calibration.avi
      sub-<B>/
        sub-<B>_ses-<label>_behavior+ecephys.nwb

The ephys goes through NeuroConv's SpikeGadgets interface, which also
supplies the device, electrode-group and electrode-table plumbing. Each
animal's file takes only that headstage's channels. Frame-pulse
synchronization, the headstage accelerometer and the Trodes comments are
follow-ups (see ``README.md``), so the videos carry a nominal rate and a
provisional starting time.

Example CLI usage
-----------------
python3 _zhang_ferret_hyperscanning_to_nwb.py \\
    --input path/to/0236HS3_0237HS4_20260401_130419.rec \\
    --output path/to/standardized/000547 --config config.yaml
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime
import os
import re
import shutil
import zoneinfo
from pathlib import Path
from xml.etree import ElementTree

import av
import numpy
import yaml
from neuroconv.datainterfaces import SpikeGadgetsRecordingInterface
from neuroconv.tools.nwb_helpers import configure_and_write_nwbfile
from pynwb.device import Device
from pynwb.image import ImageSeries

REC_NAME_PATTERN = re.compile(
    r"^(?P<subject_a>\d{4})HS(?P<headstage_a>\d+)_(?P<subject_b>\d{4})HS(?P<headstage_b>\d+)"
    r"_(?P<date>\d{8})_(?P<time>\d{6})$"
)
PAIR_DIRNAME_PATTERN = re.compile(r"^\d{4}-\d{4}$")
VIDEO_NAME_PATTERN = re.compile(
    r"^cam(?P<camera>\d+)(?P<calibration>-cal)?-(?P<stamp>\d{14})-\d{4}\.avi$", re.IGNORECASE
)
VIDEO_STAMP_FORMAT = "%m%d%Y%H%M%S"
VIDEOS_DIRNAME = "Videos"
VIDEO_KINDS = ("video", "calibration")
STREAMS_SUFFIX = "behavior+ecephys"
ELECTRICAL_SERIES_KEY = "spikegadgets_recording"
HEADER_END_TAG = b"</Configuration>"
HEADER_READ_LIMIT = 64 * 1024 * 1024


@dataclasses.dataclass(frozen=True)
class Headstage:
    """One animal's headstage as the ``.rec`` basename lists it."""

    subject: str
    headstage: str
    position: int


@dataclasses.dataclass(frozen=True)
class RecordingIdentity:
    rec_path: Path
    headstages: tuple[Headstage, Headstage]
    session_label: str
    name_start: datetime.datetime

    @property
    def pair(self):
        pair = "-".join(headstage.subject for headstage in self.headstages)
        return pair

    @property
    def host_subject(self):
        """The animal whose directory holds the shared video files."""
        host = min(headstage.subject for headstage in self.headstages)
        return host


def load_cfg(path, /):
    with open(path) as handle:
        cfg = yaml.safe_load(handle)
    return cfg


def resolve_rec_file(rec, /):
    """The Trodes file for *rec*, given either the ``.rec`` directory or the file itself."""
    rec = Path(rec)
    rec_path = rec / rec.name if rec.is_dir() else rec
    return rec_path


def derive_session_label(rec_stem, /):
    """``20260401T130419`` from ``0236HS3_0237HS4_20260401_130419``: alphanumeric, unique, sortable."""
    match = REC_NAME_PATTERN.match(rec_stem)
    if match is None:
        raise ValueError(f"not a recognized recording name: {rec_stem!r}")
    label = f"{match['date']}T{match['time']}"
    return label


def derive_subject_labels(rec_stem, /):
    """Both headstages from the ``.rec`` basename, in the order it lists them."""
    match = REC_NAME_PATTERN.match(rec_stem)
    if match is None:
        raise ValueError(f"not a recognized recording name: {rec_stem!r}")
    headstages = (
        Headstage(subject=match["subject_a"], headstage=match["headstage_a"], position=0),
        Headstage(subject=match["subject_b"], headstage=match["headstage_b"], position=1),
    )
    return headstages


def parse_rec_identity(rec, /):
    rec_path = resolve_rec_file(rec)
    match = REC_NAME_PATTERN.match(rec_path.stem)
    if match is None:
        raise ValueError(f"not a recognized recording name: {rec_path.name!r}")
    headstages = derive_subject_labels(rec_path.stem)
    pair_dirname = rec_path.parent.parent.parent.name
    expected_pair = "-".join(headstage.subject for headstage in headstages)
    if PAIR_DIRNAME_PATTERN.match(pair_dirname) and pair_dirname != expected_pair:
        raise ValueError(f"recording {rec_path.name} names pair {expected_pair} but sits under {pair_dirname}/")
    name_start = datetime.datetime.strptime(match["date"] + match["time"], "%Y%m%d%H%M%S")
    identity = RecordingIdentity(
        rec_path=rec_path,
        headstages=headstages,
        session_label=derive_session_label(rec_path.stem),
        name_start=name_start,
    )
    return identity


def read_header_creation_time(rec_path, /):
    """``systemTimeAtCreation`` from the Trodes XML header as an aware UTC datetime, or ``None``."""
    with open(rec_path, "rb") as handle:
        header = handle.read(HEADER_READ_LIMIT)
    end = header.find(HEADER_END_TAG)
    if end < 0:
        return None
    root = ElementTree.fromstring(header[: end + len(HEADER_END_TAG)].decode("utf8", errors="replace"))
    global_configuration = root.find("GlobalConfiguration")
    if global_configuration is None or "systemTimeAtCreation" not in global_configuration.attrib:
        return None
    milliseconds = int(global_configuration.attrib["systemTimeAtCreation"])
    creation_time = datetime.datetime.fromtimestamp(milliseconds / 1000.0, tz=datetime.timezone.utc)
    return creation_time


def session_start_time(*, identity, cfg):
    """The Trodes header's creation time when present, else the basename's timestamp, in the configured zone."""
    zone = zoneinfo.ZoneInfo(cfg["session"]["timezone"])
    header_time = read_header_creation_time(identity.rec_path)
    if header_time is not None:
        start_time = header_time.astimezone(zone)
    else:
        start_time = identity.name_start.replace(tzinfo=zone)
    return start_time


def match_videos(rec, /):
    """Per camera, the behavior and calibration videos nearest this recording's timestamp.

    Returns ``(matched, unmatched)``: ``matched`` maps a camera number to a
    ``{kind: path}`` dict, ``unmatched`` lists files in ``Videos/`` whose
    names the pattern does not recognize. A missing ``Videos/`` directory
    yields nothing matched.
    """
    rec_path = resolve_rec_file(rec)
    identity = parse_rec_identity(rec_path)
    videos_dir = rec_path.parent.parent / VIDEOS_DIRNAME
    matched: dict[int, dict[str, Path]] = {}
    unmatched: list[Path] = []
    if not videos_dir.is_dir():
        return matched, unmatched
    candidates: dict[tuple[int, str], list[tuple[float, Path]]] = {}
    for path in sorted(videos_dir.iterdir()):
        match = VIDEO_NAME_PATTERN.match(path.name)
        if match is None:
            unmatched.append(path)
            continue
        kind = "calibration" if match["calibration"] else "video"
        stamp = datetime.datetime.strptime(match["stamp"], VIDEO_STAMP_FORMAT)
        distance = abs((stamp - identity.name_start).total_seconds())
        candidates.setdefault((int(match["camera"]), kind), []).append((distance, path))
    for (camera, kind), options in candidates.items():
        _, nearest = min(options)
        matched.setdefault(camera, {})[kind] = nearest
    return matched, unmatched


def count_video_frames(path, /):
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        frames = stream.frames
        if not frames:
            frames = sum(1 for _ in container.demux(stream))
    return frames


def load_session_log(path, /):
    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows


def _minutes(clock, /):
    hours, minutes = clock.split(":")
    total = int(hours) * 60 + int(minutes)
    return total


def find_session_row(rows, /, *, pair, start):
    """The session-log row for *pair* on *start*'s date, nearest by start time when the day has several."""
    date = start.date().isoformat()
    candidates = [row for row in rows if row["pair"] == pair and row["date"] == date]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    rec_minutes = start.hour * 60 + start.minute
    timed = [row for row in candidates if row.get("start")]
    if not timed:
        return candidates[0]
    nearest = min(timed, key=lambda row: abs(_minutes(row["start"]) - rec_minutes))
    return nearest


def select_channel_map(*, belly_up, cfg):
    key = "belly_up" if belly_up else "belly_down"
    channel_map = cfg["ecephys"]["channel_maps"][key]
    return channel_map


def headstage_channel_ids(*, channel_ids, position, channels_per_headstage):
    """This headstage's hardware channel ids, assuming headstages occupy consecutive blocks (PROVISIONAL)."""
    low = position * channels_per_headstage
    high = low + channels_per_headstage
    selected = [channel_id for channel_id in channel_ids if low <= int(channel_id) < high]
    return selected


def output_paths(*, output_dir, identity):
    """Each animal's NWB path for this recording, keyed by subject label."""
    paths = {}
    for headstage in identity.headstages:
        subject = headstage.subject
        filename = f"sub-{subject}_ses-{identity.session_label}_{STREAMS_SUFFIX}.nwb"
        paths[subject] = Path(output_dir) / f"sub-{subject}" / filename
    return paths


def video_destination(*, output_dir, identity, camera, kind):
    host = identity.host_subject
    filename = f"sub-{host}_ses-{identity.session_label}_cam{camera}_{kind}.avi"
    destination = Path(output_dir) / f"sub-{host}" / filename
    return destination


def link_or_copy(*, source, destination):
    """Hard-link *source* to *destination* when the filesystem allows it, copy otherwise."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def place_videos(*, matched, output_dir, identity, overwrite):
    """Put the session's videos into the host subject's directory; returns ``{(camera, kind): destination}``."""
    placed = {}
    for camera, videos in sorted(matched.items()):
        for kind in VIDEO_KINDS:
            source = videos.get(kind)
            if source is None:
                continue
            destination = video_destination(output_dir=output_dir, identity=identity, camera=camera, kind=kind)
            if destination.exists() and not overwrite:
                print(f"Video exists, keeping: {destination}", flush=True)
            else:
                link_or_copy(source=source, destination=destination)
            placed[(camera, kind)] = destination
    return placed


def _subject_metadata(*, subject, cfg):
    subjects = cfg["subjects"]
    metadata = dict(subjects["defaults"])
    metadata.update(subjects.get(subject, {}))
    metadata["subject_id"] = subject
    metadata.setdefault("description", f"Ferret {subject}")
    return metadata


def build_nwbfile(*, identity, headstage, cfg, placed_videos, nwb_path, belly_up, session_row):
    """One animal's NWBFile: its headstage channels plus the shared videos."""
    partner = identity.headstages[1 - headstage.position]
    ecephys_cfg = cfg["ecephys"]
    channel_map = select_channel_map(belly_up=belly_up, cfg=cfg)

    interface = SpikeGadgetsRecordingInterface(file_path=identity.rec_path)
    recording = interface.recording_extractor
    channel_ids = headstage_channel_ids(
        channel_ids=recording.get_channel_ids(),
        position=headstage.position,
        channels_per_headstage=ecephys_cfg["channels_per_headstage"],
    )
    if not channel_ids:
        raise ValueError(
            f"no channels for headstage HS{headstage.headstage} (position {headstage.position}) in {identity.rec_path}"
        )
    subset = recording.select_channels(channel_ids)
    local_channels = numpy.array(
        [
            int(channel_id) - headstage.position * ecephys_cfg["channels_per_headstage"]
            for channel_id in subset.get_channel_ids()
        ]
    )
    regions = numpy.array([channel_map["odd" if channel % 2 else "even"] for channel in local_channels])
    subset.set_property("group_name", regions)
    subset.set_property("reference_electrode", numpy.isin(local_channels, ecephys_cfg["reference_channels"]))
    subset.set_property("headstage_channel", local_channels)
    interface.recording_extractor = subset

    device_key = "headstage"
    device_name = cfg["devices"]["headstage"]["name_template"].format(headstage=headstage.headstage)
    session_cfg = cfg["session"]
    channel_map_name = "Belly-up" if belly_up else "Belly-down"
    notes = session_cfg["notes_template"].format(
        pair=identity.pair,
        usable_data=(session_row or {}).get("usable_data") or "not logged",
        notes=(session_row or {}).get("notes") or "none",
    )

    metadata = interface.get_metadata()
    metadata["NWBFile"].update(
        {
            "session_description": session_cfg["description_template"].format(
                subject=headstage.subject,
                headstage=headstage.headstage,
                partner=partner.subject,
                partner_headstage=partner.headstage,
                channel_map=channel_map_name,
            ),
            "identifier": f"zhang-ferret-hyperscanning-{identity.session_label}-sub-{headstage.subject}",
            "session_start_time": session_start_time(identity=identity, cfg=cfg),
            "session_id": identity.session_label,
            "lab": session_cfg["lab"],
            "institution": session_cfg["institution"],
            "experimenter": list(session_cfg["experimenter"]),
            "experiment_description": session_cfg["experiment_description"],
            "keywords": list(session_cfg["keywords"]),
            "related_publications": list(session_cfg["related_publications"]),
            "notes": notes,
        }
    )
    metadata["Subject"] = _subject_metadata(subject=headstage.subject, cfg=cfg)
    metadata["Devices"] = {
        device_key: {
            "name": device_name,
            "description": cfg["devices"]["headstage"]["description"],
            "manufacturer": cfg["devices"]["headstage"]["manufacturer"],
        }
    }
    metadata["Ecephys"]["ElectrodeGroups"] = {
        region: {
            "name": region,
            "description": details["description"],
            "location": details["location"],
            "device_metadata_key": device_key,
        }
        for region, details in ecephys_cfg["regions"].items()
    }
    metadata["Ecephys"]["ElectricalSeries"][ELECTRICAL_SERIES_KEY]["description"] = ecephys_cfg[
        "electrical_series_description"
    ]
    metadata["Ecephys"]["Electrodes"] = [
        {"name": "reference_electrode", "description": ecephys_cfg["reference_note"]},
        {"name": "headstage_channel", "description": "Channel index within this animal's headstage (0-31)"},
    ]

    nwbfile = interface.create_nwbfile(metadata=metadata)
    _add_videos(nwbfile=nwbfile, cfg=cfg, placed_videos=placed_videos, nwb_path=nwb_path)
    return nwbfile


def _add_videos(*, nwbfile, cfg, placed_videos, nwb_path):
    video_cfg = cfg["video"]
    camera_cfg = cfg["devices"]["camera"]
    devices = {}
    for (camera, kind), destination in sorted(placed_videos.items()):
        if camera not in devices:
            device = Device(
                name=camera_cfg["name_template"].format(camera=camera),
                description=camera_cfg["description"],
                manufacturer=camera_cfg["manufacturer"],
            )
            nwbfile.add_device(device)
            devices[camera] = device
        relative_path = os.path.relpath(destination, nwb_path.parent)
        if kind == "video":
            name = f"BehaviorVideoCam{camera}"
            description = f"Behavior video from camera {camera} (source file {destination.name})"
        else:
            name = f"CalibrationVideoCam{camera}"
            description = (
                f"ChArUco board calibration video for camera {camera}, filmed before the session "
                f"(source file {destination.name})"
            )
        series = ImageSeries(
            name=name,
            description=description,
            external_file=[relative_path],
            format="external",
            starting_frame=[0],
            rate=float(video_cfg["rate"]),
            starting_time=float(video_cfg["starting_time"]),
            num_samples=count_video_frames(destination),
            unit="n.a.",
            device=devices[camera],
        )
        nwbfile.add_acquisition(series)


def convert_session(*, rec, output_dir, cfg, session_log=None, overwrite=False):
    """Convert one recording into its two subject files; returns the written NWB paths."""
    identity = parse_rec_identity(rec)
    output_dir = Path(output_dir)
    matched, unmatched = match_videos(identity.rec_path)
    for path in unmatched:
        print(f"Ignoring unrecognized file in {VIDEOS_DIRNAME}/: {path.name}", flush=True)
    expected_cameras = set(cfg["video"]["cameras"])
    for kind in VIDEO_KINDS:
        missing = sorted(camera for camera in expected_cameras if kind not in matched.get(camera, {}))
        if missing:
            print(f"{identity.rec_path.name}: no {kind} file for camera(s) {missing}", flush=True)

    session_row = None
    if session_log:
        session_row = find_session_row(session_log, pair=identity.pair, start=identity.name_start)
        if session_row is None:
            print(
                f"{identity.rec_path.name}: no session-log row for {identity.pair} on {identity.name_start.date()}",
                flush=True,
            )
    belly_up = bool(int(session_row["belly_up"])) if session_row else False

    placed_videos = place_videos(matched=matched, output_dir=output_dir, identity=identity, overwrite=overwrite)
    paths = output_paths(output_dir=output_dir, identity=identity)
    written = []
    for headstage in identity.headstages:
        nwb_path = paths[headstage.subject]
        nwb_path.parent.mkdir(parents=True, exist_ok=True)
        nwbfile = build_nwbfile(
            identity=identity,
            headstage=headstage,
            cfg=cfg,
            placed_videos=placed_videos,
            nwb_path=nwb_path,
            belly_up=belly_up,
            session_row=session_row,
        )
        if nwb_path.exists():
            nwb_path.unlink()
        configure_and_write_nwbfile(nwbfile, nwbfile_path=nwb_path, backend="hdf5")
        written.append(nwb_path)
    return written


def load_session_log_for(cfg, /, *, config_path):
    """The session log named in *cfg*, resolved relative to the config file; ``[]`` when unset."""
    relative = cfg.get("session_log", {}).get("path")
    if not relative:
        return []
    log_path = Path(config_path).parent / relative
    rows = load_session_log(log_path)
    return rows


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert one ferret hyperscanning .rec recording to per-subject NWB files"
    )
    parser.add_argument("--input", required=True, type=Path, help="The .rec directory (or the .rec file inside it)")
    parser.add_argument("--output", required=True, type=Path, help="Standardized output directory (DANDI layout)")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.yaml",
        help="YAML config (default: config.yaml next to this script)",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace output files that already exist")
    arguments = parser.parse_args()
    return arguments


def main():
    args = parse_args()
    cfg = load_cfg(args.config)
    session_log = load_session_log_for(cfg, config_path=args.config)
    written = convert_session(
        rec=args.input, output_dir=args.output, cfg=cfg, session_log=session_log, overwrite=args.overwrite
    )
    for path in written:
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
