"""Convert one Sanes session into a multisubject NWB file plus one NWB file per tracked animal.

Sanes recordings use either continuous ``idx_*`` chunks or a ``sync.csv`` manifest grouping simultaneous
microphones and cameras in ``concatenated_data_cam_mic_sync/``. The chunk layout is::

    <session>/
      *log_*.txt          optional, its first "Started Experiment Now" entry is the session start
      idx_<N>/
        *.wav             one file per microphone channel ("multichannel" files are skipped)
        *.mp4             the behavioral video
        *.slp             pose as SLEAP labels, or
        *.tracks.csv      pose as a SLEAP CSV export
        *annotations.csv  vocalizations (name, start_seconds, stop_seconds, channel)

Audio and video must be present in every chunk or in none. Pose and annotations may be missing from any
chunk. See ``../README.md`` for the output layout and how each data type maps into it.
"""

import ast
import csv
import datetime
import json
import os
import re
import subprocess
import tempfile
import zoneinfo
from pathlib import Path

import natsort
import ndx_multisubjects
import ndx_pose
import ndx_sound
import neuroconv.tools.hdmf
import neuroconv.tools.nwb_helpers
import numpy
import pynwb
import pynwb.event
import pynwb.file
import pynwb.image
import scipy.io.wavfile
import sleap_io
import yaml

REFERENCE_FRAME = "x and y in pixels from the top-left corner of the video frame"
SYNC_FOLDER = "concatenated_data_cam_mic_sync"
SYNC_CAMERAS = ("center", "gily_center", "gily_nest", "gily_underground", "underground")
_ISO_DURATION = r"P(?=\d|T\d)(?:\d+Y)?(?:\d+M)?(?:\d+W)?(?:\d+D)?(?:T(?=\d)(?:\d+H)?(?:\d+M)?(?:\d+(?:\.\d+)?S)?)?"
# An ISO 8601 duration, or an age range "lower/upper" or "lower/" as the NWB Subject age field allows.
ISO_AGE = re.compile(rf"{_ISO_DURATION}(?:/(?:{_ISO_DURATION})?)?")


def load_cfg(config_path, /):
    cfg = yaml.safe_load(config_path.read_text())
    return cfg


def sanitize_label(text, /):
    return re.sub(r"[^0-9A-Za-z]", "", text)


def session_label(session_dir, /):
    label = sanitize_label(session_dir.name) or "unknown"
    return label


def multisubject_path(*, output_dir, session_dir):
    label = session_label(session_dir)
    path = output_dir / "sub-multi" / f"sub-multi_ses-{label}_behavior.nwb"
    return path


def _float_or_nan(value, /):
    return float(value) if value and value.strip() else numpy.nan


def discover_chunks(session_dir, /):
    chunks = natsort.natsorted((path for path in session_dir.glob("idx_*") if path.is_dir()), key=lambda p: p.name)
    return chunks


def _chunk_audio(chunk, /):
    paths = natsort.natsorted(
        (path for path in chunk.glob("*.wav") if "multichannel" not in path.name), key=lambda p: p.name
    )
    if not paths:
        return None
    shapes = set()
    rates = set()
    dtypes = set()
    for path in paths:
        rate, data = scipy.io.wavfile.read(path, mmap=True)
        shapes.add(data.shape)
        rates.add(rate)
        dtypes.add(data.dtype)
    if len(shapes) != 1 or len(rates) != 1 or len(dtypes) != 1:
        raise ValueError(f"Audio channels are not synchronized in {chunk}")
    (shape,) = shapes
    if len(shape) != 1:
        raise ValueError(f"Expected single-channel WAV files in {chunk}, found shape {shape}")
    layout = {"paths": paths, "samples": shape[0], "rate": rates.pop(), "dtype": dtypes.pop()}
    return layout


def _chunk_video(chunk, /):
    paths = sorted(chunk.glob("*.mp4"))
    if len(paths) > 1:
        raise ValueError(f"Expected at most one MP4 in {chunk}, found {paths}")
    if not paths:
        return None
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames,r_frame_rate"]
        + ["-of", "json", str(paths[0])],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(result.stdout)["streams"][0]
    numerator, denominator = (int(value) for value in stream["r_frame_rate"].split("/"))
    video = {"path": paths[0], "frames": int(stream["nb_frames"]), "rate": numerator / denominator}
    return video


def _all_or_none(*, items, kind, session_dir):
    present = [item for item in items if item is not None]
    if present and len(present) != len(items):
        raise ValueError(f"{kind} is missing from some idx_* chunks of {session_dir}")
    return bool(present)


def _concatenate_videos(*, paths, output_path, maps=()):
    """Without *maps*, FFmpeg keeps its default streams, which is what the idx datasets were converted with."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt") as listing:
        for path in paths:
            listing.write(f"file '{path.resolve()}'\n")
        listing.flush()
        map_arguments = [argument for spec in maps for argument in ("-map", spec)]
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listing.name, "-c", "copy"]
            + map_arguments
            + [str(output_path)],
            check=True,
        )


def _session_start(*, session_dir, cfg):
    logs = sorted(session_dir.glob("*log_*.txt"))
    if len(logs) > 1:
        raise ValueError(f"Expected at most one experiment log in {session_dir}, found {logs}")
    if logs:
        for line in logs[0].read_text().splitlines():
            match = re.match(r"(?P<timestamp>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})>Started Experiment Now", line)
            if match:
                start = datetime.datetime.strptime(match["timestamp"], "%Y-%m-%d_%H-%M-%S")
                return start.replace(tzinfo=datetime.timezone.utc)
        raise ValueError(f"No 'Started Experiment Now' entry found in {logs[0]}")
    configured = cfg["session"].get("start_time")
    if configured is None:
        raise ValueError(f"{session_dir} has no experiment log and the config sets no session.start_time")
    start = datetime.datetime.fromisoformat(str(configured))
    return start


def _experiment_metadata(*, session_dir, config_path, cfg):
    selected = {}
    metadata_name = cfg.get("experiment_metadata")
    if metadata_name is None:
        return selected
    metadata = yaml.safe_load((config_path.parent / metadata_name).read_text())
    experiment_number = int(re.sub(r"\D", "", session_dir.name) or -1)
    selected.update(metadata["default"])
    for candidate in metadata["ranges"]:
        start, end = candidate["experiments"]
        if start <= experiment_number <= end:
            selected.update(candidate)
            break
    return selected


def _read_tracks_csv(path, /):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        nodes = [name.removesuffix(".x") for name in reader.fieldnames if name.endswith(".x")]
        rows = []
        for row in reader:
            points = {
                node: (
                    _float_or_nan(row.get(f"{node}.x", "")),
                    _float_or_nan(row.get(f"{node}.y", "")),
                    _float_or_nan(row.get(f"{node}.score", "")),
                )
                for node in nodes
            }
            rows.append({"track": row["track"], "frame_idx": int(float(row["frame_idx"])), "points": points})
    skeleton = {"nodes": nodes, "edges": []}
    return rows, skeleton


def _read_slp(path, /):
    labels = sleap_io.load_slp(str(path), open_videos=False)
    rows = []
    for labeled_frame in labels.labeled_frames:
        for instance in labeled_frame.predicted_instances:
            values = instance.numpy(scores=True)
            points = {
                node: tuple(float(value) for value in point)
                for node, point in zip(instance.skeleton.node_names, values)
            }
            track = instance.track.name if instance.track is not None else ""
            rows.append({"track": track, "frame_idx": int(labeled_frame.frame_idx), "points": points})
    skeleton = {"nodes": [], "edges": []}
    if labels.skeletons:
        skeleton = {"nodes": labels.skeletons[0].node_names, "edges": labels.skeletons[0].edge_names}
    return rows, skeleton


def _prefer_skeleton(current, candidate, /):
    """A SLEAP skeleton carries edges and a CSV header does not, so the first one with edges wins."""
    if current is None or (candidate is not None and candidate["edges"] and not current["edges"]):
        return candidate
    return current


def _read_chunk_pose(chunk, /):
    rows = []
    skeleton = None
    for path in natsort.natsorted([*chunk.glob("*.slp"), *chunk.glob("*.tracks.csv")], key=lambda p: p.name):
        reader = _read_slp if path.suffix == ".slp" else _read_tracks_csv
        file_rows, file_skeleton = reader(path)
        rows.extend(file_rows)
        skeleton = _prefer_skeleton(skeleton, file_skeleton)
    return rows, skeleton


def _read_chunk_annotations(chunk, /):
    rows = []
    skipped = 0
    for path in natsort.natsorted(chunk.glob("*annotations.csv"), key=lambda p: p.name):
        with path.open(newline="") as stream:
            for row in csv.DictReader(stream):
                if not row["start_seconds"].strip() or not row["stop_seconds"].strip():
                    skipped += 1
                    continue
                rows.append(
                    {
                        "name": row["name"],
                        "channel": row.get("channel", ""),
                        "start": float(row["start_seconds"]),
                        "stop": float(row["stop_seconds"]),
                    }
                )
    return rows, skipped


def _subject(*, cfg, track_index):
    subject = dict(cfg["subject"])
    overrides = cfg.get("subjects", [])
    if track_index < len(overrides):
        subject.update(overrides[track_index])
    subject["id"] = sanitize_label(str(subject.get("id", f"{track_index:02d}")))
    return subject


def _combined_video_series(*, external_file, rate, frames, cfg):
    series = pynwb.image.ImageSeries(
        name="External Behavioral Video (Combined)",
        unit="n/a",
        starting_time=0.0,
        rate=float(rate),
        external_file=[external_file],
        starting_frame=[0],
        format="external",
        num_samples=frames,
        description=cfg["video"]["description"],
    )
    return series


def _pose_estimation(*, rows, skeleton, source_video):
    rows = sorted(rows, key=lambda row: row["timestamp"])
    timestamps = numpy.asarray([row["timestamp"] for row in rows])
    nan_point = (numpy.nan, numpy.nan, numpy.nan)
    nodes = skeleton["nodes"]
    nwb_skeleton = ndx_pose.Skeleton(
        name="skeleton",
        nodes=nodes,
        edges=numpy.asarray(
            [[nodes.index(source), nodes.index(target)] for source, target in skeleton["edges"]], dtype="uint8"
        ).reshape(-1, 2),
    )
    series = []
    for node in nodes:
        values = numpy.asarray([row["points"].get(node, nan_point) for row in rows], dtype=float)
        series.append(
            ndx_pose.PoseEstimationSeries(
                name=node,
                description=f"Position of {node}",
                data=values[:, :2],
                unit="pixels",
                reference_frame=REFERENCE_FRAME,
                confidence=values[:, 2],
                confidence_definition="Point-wise confidence score from SLEAP.",
                timestamps=timestamps,
            )
        )
    pose_estimation = ndx_pose.PoseEstimation(
        name="PoseEstimation",
        description="SLEAP pose estimation on the concatenated behavioral video.",
        pose_estimation_series=series,
        skeleton=nwb_skeleton,
        source_video=source_video,
        source_software="SLEAP",
    )
    return nwb_skeleton, pose_estimation


def _write_nwbfile(*, nwbfile, path):
    backend_configuration = neuroconv.tools.nwb_helpers.get_default_backend_configuration(nwbfile, backend="hdf5")
    backend_configuration.apply_global_compression(["gzip"], [{"level": 4}])
    neuroconv.tools.nwb_helpers.configure_backend(nwbfile=nwbfile, backend_configuration=backend_configuration)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pynwb.NWBHDF5IO(path, "w") as io:
        io.write(nwbfile)


def _write_track_nwbs(*, track_rows, skeleton, output_dir, label, session_start, video, cfg):
    written = []
    for track_index, track in enumerate(natsort.natsorted(track_rows)):
        subject = _subject(cfg=cfg, track_index=track_index)
        track_path = output_dir / f"sub-{subject['id']}" / f"sub-{subject['id']}_ses-{label}.nwb"
        track_nwb = pynwb.NWBFile(
            session_description=f"Pose of the animal tracked as '{track}'",
            identifier=f"sanes-{cfg['session']['dataset']}-{label}-sub-{subject['id']}",
            session_start_time=session_start,
            experimenter=cfg["session"]["experimenter"],
            institution=cfg["session"]["institution"],
            lab=cfg["session"]["lab"],
            subject=pynwb.file.Subject(
                subject_id=subject["id"],
                description=subject.get("description", f"Animal tracked as '{track}' in this session."),
                species=subject["species"],
                sex=subject["sex"],
                age=subject["age"],
            ),
        )
        video_series = _combined_video_series(
            external_file=os.path.relpath(video["path"], track_path.parent),
            rate=video["rate"],
            frames=video["frames"],
            cfg=cfg,
        )
        track_nwb.add_acquisition(video_series)
        behavior = track_nwb.create_processing_module(name="behavior", description="Pose estimation")
        nwb_skeleton, pose_estimation = _pose_estimation(
            rows=track_rows[track], skeleton=skeleton, source_video=video_series
        )
        behavior.add(ndx_pose.Skeletons(skeletons=[nwb_skeleton]))
        behavior.add(pose_estimation)
        _write_nwbfile(nwbfile=track_nwb, path=track_path)
        written.append((subject, track_path))
    return written


def build_nwb(*, session_dir, output_dir, config_path):
    cfg = load_cfg(config_path)
    if (session_dir / SYNC_FOLDER).is_dir():
        if discover_chunks(session_dir):
            raise ValueError(f"Ambiguous session with both idx_* chunks and {SYNC_FOLDER}: {session_dir}")
        output_path = _build_synced_nwb(session_dir=session_dir, output_dir=output_dir, cfg=cfg)
        return output_path
    chunks = discover_chunks(session_dir)
    if not chunks:
        raise ValueError(f"No idx_* chunks found under {session_dir}")
    label = session_label(session_dir)
    output_path = multisubject_path(output_dir=output_dir, session_dir=session_dir)
    session_start = _session_start(session_dir=session_dir, cfg=cfg)
    experiment_metadata = _experiment_metadata(session_dir=session_dir, config_path=config_path, cfg=cfg)

    audio_layouts = [_chunk_audio(chunk) for chunk in chunks]
    videos = [_chunk_video(chunk) for chunk in chunks]
    has_audio = _all_or_none(items=audio_layouts, kind="Audio", session_dir=session_dir)
    has_video = _all_or_none(items=videos, kind="Video", session_dir=session_dir)
    if not has_audio and not has_video:
        raise ValueError(f"No audio or video found in {session_dir}")
    if has_audio:
        first = audio_layouts[0]
        if any(
            (len(layout["paths"]), layout["rate"], layout["dtype"])
            != (len(first["paths"]), first["rate"], first["dtype"])
            for layout in audio_layouts
        ):
            raise ValueError(
                f"Audio channel count, sampling rate, or sample type changes between chunks of {session_dir}"
            )
    if has_video and any(video["rate"] != videos[0]["rate"] for video in videos):
        raise ValueError(f"Video frame rate changes between chunks of {session_dir}")

    nwbfile = ndx_multisubjects.NdxMultiSubjectsNWBFile(
        session_description=experiment_metadata.get("description", cfg["session"]["description"]),
        identifier=f"sanes-{cfg['session']['dataset']}-{session_dir.name}",
        session_start_time=session_start,
        experimenter=cfg["session"]["experimenter"],
        institution=cfg["session"]["institution"],
        lab=cfg["session"]["lab"],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_audio_path = output_path.with_suffix(".audio.tmp")
    audio_data = None
    if has_audio:
        audio_data = numpy.memmap(
            temporary_audio_path,
            dtype=audio_layouts[0]["dtype"],
            mode="w+",
            shape=(sum(layout["samples"] for layout in audio_layouts), len(audio_layouts[0]["paths"])),
        )
    try:
        annotation_rows = []
        skipped_annotations = 0
        track_rows = {}
        skeleton = None
        audio_cursor = 0
        frame_cursor = 0
        for chunk, audio_layout, video in zip(chunks, audio_layouts, videos):
            if has_audio:
                for channel_index, path in enumerate(audio_layout["paths"]):
                    _, data = scipy.io.wavfile.read(path, mmap=True)
                    audio_data[audio_cursor : audio_cursor + audio_layout["samples"], channel_index] = data
                chunk_offset = audio_cursor / audio_layout["rate"]
                audio_cursor += audio_layout["samples"]
            else:
                chunk_offset = frame_cursor / video["rate"]

            chunk_annotations, chunk_skipped = _read_chunk_annotations(chunk)
            skipped_annotations += chunk_skipped
            for row in chunk_annotations:
                annotation_rows.append(
                    {**row, "start": row["start"] + chunk_offset, "stop": row["stop"] + chunk_offset}
                )

            pose_rows, chunk_skeleton = _read_chunk_pose(chunk)
            if pose_rows and not has_video:
                raise ValueError(f"Pose in {chunk} needs the chunk video to place frames in time")
            # Pose frame indices count frames of this chunk's video, so they are placed on the
            # concatenated video's clock, the same clock the combined ImageSeries uses.
            for row in pose_rows:
                timestamp = (frame_cursor + row["frame_idx"]) / video["rate"]
                track_rows.setdefault(row["track"], []).append({**row, "timestamp": timestamp})
            skeleton = _prefer_skeleton(skeleton, chunk_skeleton)
            if has_video:
                frame_cursor += video["frames"]

        if has_audio:
            audio_data.flush()
            nwbfile.add_acquisition(
                ndx_sound.AcousticWaveformSeries(
                    name="Multi-channel Acoustic Data",
                    data=audio_data,
                    rate=float(audio_layouts[0]["rate"]),
                    description=cfg["audio"]["description"],
                )
            )

        combined_video = None
        if has_video:
            combined_video = {
                "path": output_path.with_name(f"sub-multi_ses-{label}_video.mp4"),
                "rate": videos[0]["rate"],
                "frames": frame_cursor,
            }
            _concatenate_videos(paths=[video["path"] for video in videos], output_path=combined_video["path"])
            nwbfile.add_acquisition(
                _combined_video_series(
                    external_file=combined_video["path"].name,
                    rate=combined_video["rate"],
                    frames=combined_video["frames"],
                    cfg=cfg,
                )
            )

        track_nwbs = _write_track_nwbs(
            track_rows=track_rows,
            skeleton=skeleton,
            output_dir=output_dir,
            label=label,
            session_start=session_start,
            video=combined_video,
            cfg=cfg,
        )
        if track_nwbs:
            subjects_table = ndx_multisubjects.SubjectsTable(description="Animals tracked in this session")
            for subject, track_path in track_nwbs:
                subjects_table.add_row(
                    species=subject["species"],
                    subject_id=subject["id"],
                    sex=subject["sex"],
                    age=subject["age"],
                    individual_subj_link=os.path.relpath(track_path, output_path.parent),
                )
            nwbfile.subjects_table = subjects_table

        if annotation_rows:
            behavior = nwbfile.create_processing_module(name="behavior", description="Vocalization annotations")
            events = pynwb.event.EventsTable(
                name="vocalizations",
                description="Vocalization onsets with durations, offset onto the concatenated session clock.",
                source_description="Per-chunk vocalization annotation CSVs",
            )
            events.add_column(name="label", description="Vocalization annotation label.")
            events.add_column(name="channel", description="Microphone channel.")
            for row in annotation_rows:
                events.add_event(
                    timestamp=row["start"],
                    duration=row["stop"] - row["start"],
                    label=row["name"],
                    channel=row["channel"],
                )
            behavior.add(events)
        if skipped_annotations:
            print(f"Skipped {skipped_annotations} incomplete annotation row(s) in {session_dir}")

        _write_nwbfile(nwbfile=nwbfile, path=output_path)
    finally:
        del audio_data
        temporary_audio_path.unlink(missing_ok=True)
    return output_path


def _manifest_list(*, value, field):
    try:
        items = ast.literal_eval(value)
    except (ValueError, SyntaxError, TypeError) as error:
        raise ValueError(f"Invalid sync.csv {field} list") from error
    if not isinstance(items, list) or not items or not all(isinstance(item, str) for item in items):
        raise ValueError(f"sync.csv {field} must be a nonempty list of strings")
    return items


def _read_sync_manifest(*, folder, timezone):
    rows = []
    seen = set()
    with (folder / "sync.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["video", "audio", "timestamp"]:
            raise ValueError("sync.csv must have video,audio,timestamp columns")
        for record in reader:
            values = {field: _manifest_list(value=record[field], field=field) for field in reader.fieldnames}
            if len(values["timestamp"]) != 2:
                raise ValueError("Each sync.csv timestamp must contain start and end")
            start, stop = [datetime.datetime.fromisoformat(value) for value in values["timestamp"]]
            if any(value.tzinfo is not None for value in (start, stop)):
                raise ValueError("Expected local timestamps without offsets in sync.csv")
            audio = {}
            videos = {}
            segment_ids = set()
            for kind, pattern, destination, suffix in (
                ("audio", r"channel_(0[0-7])_file_(\d{3})", audio, ".wav"),
                ("video", r"video_(center|gily_center|gily_nest|gily_underground|underground)_(\d{3})", videos, ".mp4"),
            ):
                for name in values[kind]:
                    match = re.fullmatch(pattern, name)
                    if match is None or name in seen or match[1] in destination:
                        raise ValueError(f"Invalid or duplicate sync.csv filename: {name}")
                    seen.add(name)
                    segment_ids.add(match[2])
                    path = folder / (name + suffix)
                    if not path.is_file():
                        raise ValueError(f"Missing manifest media: {path}")
                    destination[match[1]] = path
            if set(audio) != {f"{index:02d}" for index in range(8)} or set(videos) != set(SYNC_CAMERAS):
                raise ValueError("Each sync.csv row needs eight microphones and five camera views")
            if len(segment_ids) != 1 or stop <= start:
                raise ValueError("Inconsistent segment suffixes or invalid time interval in sync.csv")
            rows.append({"start": start, "stop": stop, "segment": segment_ids.pop(), "audio": audio, "videos": videos})
    if not rows:
        raise ValueError("sync.csv contains no segments")
    rows.sort(key=lambda row: row["start"])
    for previous, current in zip(rows, rows[1:]):
        if previous["stop"] != current["start"]:
            raise ValueError("sync.csv segments overlap or have a gap")
    readme = (folder / "README.txt").read_text()
    descriptions = []
    for line in readme.splitlines():
        if not line.startswith("[video_"):
            continue
        groups = line.split(" - ")
        if len(groups) != 3:
            raise ValueError("Malformed synchronization description in README.txt")
        videos, audio, timestamps = [group.strip("[]").split(", ") for group in groups]
        descriptions.append((set(videos), set(audio), timestamps))
    expected = [
        (
            {path.stem for path in row["videos"].values()},
            {path.stem for path in row["audio"].values()},
            [row[key].isoformat(sep=" ") for key in ("start", "stop")],
        )
        for row in rows
    ]
    if len(descriptions) != len(expected) or any(item not in descriptions for item in expected):
        raise ValueError("README.txt synchronization descriptions disagree with sync.csv")
    zone = zoneinfo.ZoneInfo(timezone)
    for row in rows:
        for key in ("start", "stop"):
            local = row[key]
            aware = local.replace(tzinfo=zone)
            if aware.utcoffset() != local.replace(tzinfo=zone, fold=1).utcoffset():
                raise ValueError("Ambiguous or nonexistent local time in sync.csv. Confirm the timestamp offsets.")
            row[key] = aware
    origin = rows[0]["start"].timestamp()
    for row in rows:
        row["offset"] = row["start"].timestamp() - origin
        row["duration"] = row["stop"].timestamp() - row["start"].timestamp()
        if row["duration"] <= 0:
            raise ValueError("Non-positive elapsed segment duration")
    included = {path.name for row in rows for kind in ("audio", "videos") for path in row[kind].values()}
    for path in sorted(folder.iterdir()):
        if path.name not in {"README.txt", "sync.csv"} and path.name not in included:
            print(f"Out of scope: {path}", flush=True)
    return rows


def _describe_stream(stream, /):
    codec = stream.get("codec_name") or stream.get("codec_tag_string") or "unknown codec"
    description = f"{stream['codec_type']} ({codec})"
    return description


def _probe_sync_video(path, /):
    """Frame presentation times, read from packets without decoding, plus the file's other streams.

    ``timestamps`` start at zero. ``first_pts`` is where the first frame sits inside the file.
    """
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_entries", "packet=stream_index,pts_time,flags"]
        + ["-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    video_streams = [stream for stream in streams if stream["codec_type"] == "video"]
    if len(video_streams) != 1:
        raise ValueError(f"Expected exactly one video stream in {path}, found {len(video_streams)}")
    stream = video_streams[0]
    try:
        timestamps = numpy.sort(
            [
                float(packet["pts_time"])
                for packet in info.get("packets", [])
                if packet["stream_index"] == stream["index"] and "D" not in packet.get("flags", "")
            ]
        )
    except ValueError as error:
        raise ValueError(f"Invalid frame presentation times in {path}") from error
    if not len(timestamps):
        raise ValueError(f"No video frames in {path}")
    if not numpy.isfinite(timestamps).all() or numpy.any(numpy.diff(timestamps) <= 0):
        raise ValueError(f"Invalid frame presentation times in {path}")
    first_pts = float(timestamps[0])
    timestamps -= first_pts
    duration = float(stream.get("duration", "nan"))
    if not numpy.isfinite(duration) or duration <= timestamps[-1]:
        raise ValueError(f"Invalid video duration in {path}")
    numerator, denominator = map(int, stream["r_frame_rate"].split("/"))
    rate = numerator / denominator if denominator else 0
    if rate <= 0:
        raise ValueError(f"Invalid video rate in {path}")
    kept = [item for item in streams if item["codec_type"] in ("video", "audio")]
    signature = (
        tuple(stream.get(key) for key in ("codec_name", "width", "height", "pix_fmt", "time_base", "extradata_size")),
        tuple(_describe_stream(item) for item in kept),
    )
    probe = {
        "path": path,
        "timestamps": timestamps,
        "first_pts": first_pts,
        "duration": duration,
        "signature": signature,
        "rate": rate,
        "embedded_audio": [_describe_stream(item) for item in streams if item["codec_type"] == "audio"],
        "dropped": [_describe_stream(item) for item in streams if item["codec_type"] not in ("video", "audio")],
    }
    return probe


def _check_sync_timing(*, actual, expected, tolerance, description):
    residual = actual - expected
    if not numpy.isfinite(residual) or abs(residual) > tolerance + 1e-6:
        raise ValueError(f"Timing conflict for {description}: measured {actual:g}s, expected {expected:g}s")
    return residual


def _camera_timeline(*, camera, rows, segments):
    """Session times of every frame: the segment's manifest start plus the frame's offset from the segment's first."""
    for row, following, segment in zip(rows, rows[1:], segments):
        last = row["offset"] + segment["timestamps"][-1]
        if last >= following["offset"]:
            raise ValueError(
                f"{camera} segment {row['segment']} has a frame at {last:g}s, at or past the next segment's manifest "
                f"start at {following['offset']:g}s. Ask the requester whether to trim, shift, or keep these frames."
            )
    timestamps = numpy.concatenate([row["offset"] + segment["timestamps"] for row, segment in zip(rows, segments)])
    return timestamps


def _check_remux(*, camera, combined, segments):
    """FFmpeg places each segment after the previous one's container duration, so check each segment on its own."""
    counts = [len(segment["timestamps"]) for segment in segments]
    if len(combined["timestamps"]) != sum(counts):
        raise ValueError(f"Remux changed the frame count for {camera}")
    bounds = numpy.cumsum([0, *counts])
    for segment, start, stop in zip(segments, bounds[:-1], bounds[1:]):
        remuxed = combined["timestamps"][start:stop] - combined["timestamps"][start]
        if not numpy.allclose(remuxed, segment["timestamps"], atol=1e-5, rtol=0):
            raise ValueError(f"Remux changed the frame presentation times of {segment['path'].name}")


def _video_description(*, camera, segments, cfg):
    embedded = segments[0]["embedded_audio"]
    dropped = sorted({stream for segment in segments for stream in segment["dropped"]})
    offset = max(segment["first_pts"] for segment in segments)
    description = f"{cfg['video']['description']}. Source camera video_{camera}. Lossless remux of the source segments."
    if embedded:
        description += f" Embedded {', '.join(embedded)} is kept in the MP4 and not converted to NWB."
        print(f"video_{camera} carries embedded {', '.join(embedded)}, kept in the MP4", flush=True)
    else:
        description += " No embedded audio."
    if dropped:
        description += f" Dropped embedded {', '.join(dropped)}."
        print(f"video_{camera} drops embedded {', '.join(dropped)}", flush=True)
    if offset > 0:
        print(
            f"video_{camera} segments start up to {offset:g}s into their files, recorded in source_segments", flush=True
        )
    return description


def _sync_subjects(*, nwbfile, session_dir, cfg):
    roster = cfg.get("session_subjects", {}).get(session_dir.name, [])
    if not roster:
        print(f"PROVISIONAL: no animal metadata for {session_dir.name}. No subjects invented.", flush=True)
        return
    # Both columns are optional as a whole, so each is written only when every animal has a real value for it.
    fields = [field for field in ("age", "date_of_birth") if any(animal.get(field) for animal in roster)]
    for field in fields:
        missing = [str(animal["id"]) for animal in roster if not animal.get(field)]
        if missing:
            raise ValueError(f"{field} is given for some animals but not for {', '.join(missing)}")
    if not fields:
        raise ValueError("Every animal needs age or date_of_birth")
    table = ndx_multisubjects.SubjectsTable(description="Animals present in this recording, supplied by the lab")
    identifiers = set()
    for animal in roster:
        original_id = str(animal["id"])
        subject_id = sanitize_label(original_id)
        if not subject_id or subject_id in identifiers:
            raise ValueError(f"Empty or colliding animal ID: {original_id}")
        identifiers.add(subject_id)
        species = animal["species"]
        sex = animal["sex"]
        if not species or "PROVISIONAL" in species or sex not in {"M", "F", "O", "U"}:
            raise ValueError(f"Invalid species or sex for {original_id}")
        metadata = {}
        if "age" in fields:
            if ISO_AGE.fullmatch(str(animal["age"])) is None:
                raise ValueError(f"Invalid ISO 8601 age for {original_id}: {animal['age']}")
            metadata["age"] = str(animal["age"])
        if "date_of_birth" in fields:
            # YAML reads an unquoted timestamp as a datetime and a bare date as a date, so go through str().
            birth = datetime.datetime.fromisoformat(str(animal["date_of_birth"]))
            if birth.tzinfo is None:
                raise ValueError(f"date_of_birth for {original_id} needs a time with a UTC offset")
            if birth > nwbfile.session_start_time:
                raise ValueError(f"date_of_birth for {original_id} is after the session start")
            metadata["date_of_birth"] = birth.isoformat()
        table.add_row(
            subject_id=subject_id,
            subject_description=f"Original lab animal ID: {original_id}",
            species=species,
            sex=sex,
            **metadata,
        )
    nwbfile.subjects_table = table


def _build_synced_nwb(*, session_dir, output_dir, cfg):
    folder = session_dir / SYNC_FOLDER
    rows = _read_sync_manifest(folder=folder, timezone=cfg["session"]["timezone"])
    tolerance = float(cfg.get("sync", {}).get("tolerance", 0))
    if not numpy.isfinite(tolerance) or tolerance < 0:
        raise ValueError("sync.tolerance must be finite and nonnegative")
    layouts = []
    videos = {camera: [] for camera in SYNC_CAMERAS}
    cursor = 0
    reference = None
    for row in rows:
        paths = [row["audio"][f"{channel:02d}"] for channel in range(8)]
        shapes = set()
        for path in paths:
            rate, data = scipy.io.wavfile.read(path, mmap=True)
            if data.ndim != 1 or not len(data) or rate <= 0:
                raise ValueError(f"Expected nonempty mono WAV: {path}")
            shapes.add((len(data), rate, data.dtype))
        if len(shapes) != 1:
            raise ValueError(f"Audio channels are not synchronized in segment {row['segment']}")
        samples, rate, dtype = shapes.pop()
        if reference is None:
            reference = (rate, dtype)
        if reference != (rate, dtype):
            raise ValueError("Audio sample rate or type changes between sync.csv segments")
        row["audio_start_residual"] = _check_sync_timing(
            actual=cursor / rate,
            expected=row["offset"],
            tolerance=tolerance,
            description=f"audio start {row['segment']}",
        )
        row["audio_duration_residual"] = _check_sync_timing(
            actual=samples / rate,
            expected=row["duration"],
            tolerance=tolerance,
            description=f"audio duration {row['segment']}",
        )
        layouts.append({"paths": paths, "samples": samples})
        row["sample_start"] = cursor
        cursor += samples
        _check_sync_timing(
            actual=cursor / rate,
            expected=row["offset"] + row["duration"],
            tolerance=tolerance,
            description=f"audio end {row['segment']}",
        )
        for camera in SYNC_CAMERAS:
            video = _probe_sync_video(row["videos"][camera])
            if videos[camera] and video["signature"] != videos[camera][0]["signature"]:
                raise ValueError(f"Incompatible video encoding or stream layout across segments for {camera}")
            video["residual"] = _check_sync_timing(
                actual=video["duration"],
                expected=row["duration"],
                tolerance=tolerance,
                description=f"{camera} duration {row['segment']}",
            )
            videos[camera].append(video)
    timelines = {camera: _camera_timeline(camera=camera, rows=rows, segments=videos[camera]) for camera in SYNC_CAMERAS}
    output_path = multisubject_path(output_dir=output_dir, session_dir=session_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nwbfile = ndx_multisubjects.NdxMultiSubjectsNWBFile(
        session_description=cfg["session"]["description"],
        identifier=f"sanes-{cfg['session']['dataset']}-{session_dir.name}",
        session_id=session_label(session_dir),
        session_start_time=rows[0]["start"],
        lab=cfg["session"]["lab"],
        institution=cfg["session"]["institution"],
        experimenter=cfg["session"]["experimenter"],
        related_publications=cfg["session"].get("related_publications", []),
        notes=(
            "PROVISIONAL metadata. Confirm recording timezone, animal roster, "
            "acquisition hardware, and audio calibration before final upload."
        ),
    )
    _sync_subjects(nwbfile=nwbfile, session_dir=session_dir, cfg=cfg)
    for channel in range(8):
        nwbfile.create_device(
            name=f"microphone_{channel:02d}",
            description=(
                f"Microphone recorded as channel_{channel:02d}. PROVISIONAL: model, placement, and calibration "
                "not yet supplied by the lab."
            ),
        )
    for camera in SYNC_CAMERAS:
        nwbfile.create_device(
            name=f"camera_{camera}",
            description=(
                f"Camera recorded as video_{camera}. PROVISIONAL: model and placement not yet supplied by the lab."
            ),
        )
    nwbfile.add_scratch(
        (folder / "sync.csv").read_text(),
        name="source_sync_csv",
        description="Original source synchronization manifest",
    )
    nwbfile.add_scratch(
        (folder / "README.txt").read_text(),
        name="source_readme",
        description="Original source synchronization documentation",
    )
    intervals = nwbfile.create_time_intervals(
        name="source_segments",
        description="Source segment associations, measured boundaries, and residuals against the manifest in seconds",
    )
    for name, description in (
        ("segment_id", "Source segment suffix"),
        ("sample_start", "First sample index in concatenated audio"),
        ("sample_count", "Samples per microphone in this segment"),
        ("audio_start_residual", "Measured audio start minus manifest start in seconds"),
        ("audio_duration_residual", "Measured audio duration minus manifest duration in seconds"),
    ):
        intervals.add_column(name=name, description=description)
    intervals.add_column(
        name="audio_files", description="Original microphone filenames in numeric channel order", index=True
    )
    intervals.add_column(
        name="video_files", description="Original video filenames in documented camera order", index=True
    )
    for camera in SYNC_CAMERAS:
        intervals.add_column(name=f"{camera}_frames", description=f"Source frame count for {camera}")
        intervals.add_column(
            name=f"{camera}_duration_residual",
            description=f"Measured {camera} duration minus manifest duration in seconds",
        )
        intervals.add_column(
            name=f"{camera}_first_pts",
            description=(
                f"Presentation time of the first {camera} frame inside its source file, in seconds. Frames are "
                "placed from the manifest start, so this offset is recorded but not applied."
            ),
        )
    for index, (row, layout) in enumerate(zip(rows, layouts)):
        metadata = {}
        for camera in SYNC_CAMERAS:
            metadata[f"{camera}_frames"] = len(videos[camera][index]["timestamps"])
            metadata[f"{camera}_duration_residual"] = videos[camera][index]["residual"]
            metadata[f"{camera}_first_pts"] = videos[camera][index]["first_pts"]
        intervals.add_interval(
            start_time=row["offset"],
            stop_time=row["offset"] + row["duration"],
            segment_id=row["segment"],
            sample_start=row["sample_start"],
            sample_count=layout["samples"],
            audio_start_residual=row["audio_start_residual"],
            audio_duration_residual=row["audio_duration_residual"],
            audio_files=[path.name for path in layout["paths"]],
            video_files=[row["videos"][camera].name for camera in SYNC_CAMERAS],
            **metadata,
        )
    with tempfile.TemporaryDirectory(prefix=".sync-", dir=output_path.parent) as temporary:
        staging = Path(temporary)
        audio_data = numpy.memmap(staging / "audio.tmp", mode="w+", dtype=reference[1], shape=(cursor, 8))
        cursor = 0
        for layout in layouts:
            for channel, path in enumerate(layout["paths"]):
                _, samples = scipy.io.wavfile.read(path, mmap=True)
                audio_data[cursor : cursor + layout["samples"], channel] = samples
            cursor += layout["samples"]
        audio_data.flush()
        nwbfile.add_acquisition(
            ndx_sound.AcousticWaveformSeries(
                name="Multi-channel Acoustic Data",
                data=neuroconv.tools.hdmf.SliceableDataChunkIterator(data=audio_data, buffer_gb=0.01),
                rate=float(reference[0]),
                starting_time=0.0,
                unit="n.a.",
                description=(
                    f"{cfg['audio']['description']}. Columns 0 to 7 are source microphones channel_00 to "
                    "channel_07, devices microphone_00 to microphone_07. Uncalibrated digital samples, with no "
                    "pressure or voltage conversion applied."
                ),
            )
        )
        for camera, segments in videos.items():
            filename = f"sub-multi_ses-{session_label(session_dir)}_recording-{sanitize_label(camera)}_video.mp4"
            combined_path = staging / filename
            _concatenate_videos(
                paths=[segment["path"] for segment in segments], output_path=combined_path, maps=("0:v", "0:a?")
            )
            _check_remux(camera=camera, combined=_probe_sync_video(combined_path), segments=segments)
            timestamps = timelines[camera]
            timing = {"timestamps": timestamps}
            rate = segments[0]["rate"]
            if numpy.allclose(timestamps, numpy.arange(len(timestamps)) / rate, atol=1e-5, rtol=0):
                timing = {"starting_time": 0.0, "rate": rate}
            nwbfile.add_acquisition(
                pynwb.image.ImageSeries(
                    name=f"video_{camera}",
                    unit="n/a",
                    external_file=[filename],
                    starting_frame=[0],
                    format="external",
                    num_samples=len(timestamps),
                    description=_video_description(camera=camera, segments=segments, cfg=cfg),
                    device=nwbfile.devices[f"camera_{camera}"],
                    **timing,
                )
            )
        staged_nwb = staging / output_path.name
        _write_nwbfile(nwbfile=nwbfile, path=staged_nwb)
        del audio_data
        for video_path in staging.glob("*.mp4"):
            video_path.replace(output_path.parent / video_path.name)
        staged_nwb.replace(output_path)
    return output_path
