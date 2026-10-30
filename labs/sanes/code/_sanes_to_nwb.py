"""Convert one Sanes session into a multisubject NWB file plus one NWB file per tracked animal.

Every Sanes dataset shares one source structure, a session folder of ``idx_*`` recording chunks that are
continuous with each other. The datasets differ only in which data types the chunks hold, so a session is
converted from whatever is present::

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

import csv
import datetime
import json
import os
import re
import subprocess
import tempfile

import natsort
import ndx_multisubjects
import ndx_pose
import ndx_sound
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


def _concatenate_videos(*, paths, output_path):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt") as listing:
        for path in paths:
            listing.write(f"file '{path.resolve()}'\n")
        listing.flush()
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listing.name, "-c", "copy"]
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
