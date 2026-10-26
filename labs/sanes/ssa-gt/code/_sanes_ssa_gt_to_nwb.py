"""Convert one SSA GT experiment into a multi-animal NWB file."""

import csv
import datetime
import json
import re
import subprocess
import tempfile

import ndx_multisubjects
import ndx_sound
import numpy
import pynwb
import scipy.io.wavfile
import yaml
from neuroconv.tools.nwb_helpers import get_default_backend_configuration
from pynwb import NWBHDF5IO, NWBFile, TimeSeries
from pynwb.behavior import EventsTable
from pynwb.file import Subject


def sanitize_label(text, /):
    return re.sub(r"[^0-9A-Za-z]", "", text)


def _float_or_nan(value, /):
    return float(value) if value and value.strip() else numpy.nan


def _read_audio(path, /):
    rate, values = scipy.io.wavfile.read(path)
    return values, rate


def _read_audio_chunk(chunk, /):
    paths = sorted(chunk.glob("channel_*_*.wav"))
    channels = [_read_audio(path) for path in paths]
    if not channels:
        raise ValueError(f"No channel WAV files found in {chunk}")
    rates = {rate for _, rate in channels}
    lengths = {len(data) for data, _ in channels}
    if len(rates) != 1 or len(lengths) != 1:
        raise ValueError(f"Audio channels are not synchronized in {chunk}")
    return numpy.column_stack([data for data, _ in channels]), channels[0][1]


def _audio_shape(chunk, /):
    paths = sorted(chunk.glob("channel_*_*.wav"))
    if not paths:
        raise ValueError(f"No channel WAV files found in {chunk}")
    channel_shapes = []
    rate = None
    for path in paths:
        this_rate, data = scipy.io.wavfile.read(path, mmap=True)
        if rate is not None and this_rate != rate:
            raise ValueError(f"Audio sampling-rate mismatch in {chunk}")
        rate = this_rate
        channel_shapes.append(data.shape[0])
    if len(set(channel_shapes)) != 1:
        raise ValueError(f"Audio channels are not synchronized in {chunk}")
    return channel_shapes[0], len(paths), rate, data.dtype


def _video_info(path, /):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_frames,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(result.stdout)["streams"][0]
    numerator, denominator = (int(value) for value in stream["r_frame_rate"].split("/"))
    return int(stream["nb_frames"]), numerator / denominator


def _concatenate_videos(paths, output_path, /):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt") as listing:
        for path in paths:
            listing.write(f"file '{path.resolve()}'\n")
        listing.flush()
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing.name, "-c", "copy", str(output_path)],
            check=True,
        )


def _session_start(experiment_dir, /):
    logs = sorted(experiment_dir.glob("*log_*.txt"))
    if len(logs) != 1:
        raise ValueError(f"Expected one experiment log in {experiment_dir}, found {logs}")
    for line in logs[0].read_text().splitlines():
        match = re.match(r"(?P<timestamp>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})>Started Experiment Now", line)
        if match:
            return datetime.datetime.strptime(match["timestamp"], "%Y-%m-%d_%H-%M-%S").replace(
                tzinfo=datetime.timezone.utc
            )
    raise ValueError(f"No 'Started Experiment Now' entry found in {logs[0]}")


def _experiment_metadata(experiment_dir, config_path, /):
    metadata_path = config_path.with_name("experiment_metadata.yaml")
    metadata = yaml.safe_load(metadata_path.read_text())
    experiment_number = int(experiment_dir.name.split("_")[-1])
    selected = dict(metadata["default"])
    for candidate in metadata["ranges"]:
        start, end = candidate["experiments"]
        if start <= experiment_number <= end:
            selected.update(candidate)
            break
    return selected


def _add_tracking(processing, csv_paths, /):
    by_track = {}
    for csv_path in csv_paths:
        with csv_path.open(newline="") as stream:
            for row in csv.DictReader(stream):
                by_track.setdefault(row["track"], []).append(row)
    for track, rows in sorted(by_track.items()):
        interface = TimeSeries(
            name=f"tracking_{sanitize_label(track) or 'unknown'}",
            data=numpy.asarray(
                [[_float_or_nan(row.get("nose.x", "")), _float_or_nan(row.get("nose.y", ""))] for row in rows]
            ),
            unit="pixels",
            timestamps=numpy.asarray([float(row["frame_idx"]) for row in rows]),
            description="Nose x/y tracking from annotation CSV; full landmark fields are retained in the source CSV.",
        )
        processing.add(interface)
    return sorted(by_track)


def _tracking_rows(csv_paths, /):
    by_track = {}
    for csv_path in csv_paths:
        with csv_path.open(newline="") as stream:
            for row in csv.DictReader(stream):
                by_track.setdefault(row["track"], []).append(row)
    return by_track


def _write_track_nwbs(*, tracking_paths, output_dir, session_label, session_start, cfg):
    track_rows = _tracking_rows(tracking_paths)
    written = []
    for track_index, (track, rows) in enumerate(sorted(track_rows.items())):
        subject_label = f"{track_index:02d}"
        track_path = output_dir / f"sub-{subject_label}_ses-{session_label}.nwb"
        track_nwb = NWBFile(
            session_description=f"Tracking data for {track}",
            identifier=f"sanes-ssa-gt-{session_label}-track-{subject_label}",
            session_start_time=session_start,
            experimenter=cfg["session"]["experimenter"],
            institution=cfg["session"]["institution"],
            lab=cfg["session"]["lab"],
            subject=Subject(
                subject_id=track,
                species=cfg["subject"]["species"],
                sex=cfg["subject"]["sex"],
                age=cfg["subject"]["age"],
            ),
        )
        behavior = track_nwb.create_processing_module(name="behavior", description="Tracking annotations")
        behavior.add(
            TimeSeries(
                name="tracking",
                data=numpy.asarray(
                    [[_float_or_nan(row.get("nose.x", "")), _float_or_nan(row.get("nose.y", ""))] for row in rows]
                ),
                unit="pixels",
                timestamps=numpy.asarray([float(row["frame_idx"]) for row in rows]),
                description="Nose x/y tracking for this animal; source CSV contains all landmarks and confidence scores.",
            )
        )
        track_backend = get_default_backend_configuration(track_nwb, backend="hdf5")
        track_backend.apply_global_compression(compression_method="gzip", compression_options={"compression_opts": 4})
        with NWBHDF5IO(track_path, "w") as io:
            io.write(track_nwb)
        written.append((track, track_path))
    return written


def build_nwb(*, experiment_dir, output_path, config_path):
    cfg = yaml.safe_load(config_path.read_text())
    experiment_metadata = _experiment_metadata(experiment_dir, config_path)
    chunks = sorted(experiment_dir.glob("idx_*"), key=lambda path: int(path.name.split("_")[-1]))
    if not chunks:
        raise ValueError(f"No idx_* chunks found under {experiment_dir}")
    nwbfile = ndx_multisubjects.NdxMultiSubjectsNWBFile(
        session_description=experiment_metadata.get("description", cfg["session"]["description"]),
        identifier=f"sanes-ssa-gt-{experiment_dir.name}",
        session_start_time=_session_start(experiment_dir),
        experimenter=cfg["session"]["experimenter"],
        institution=cfg["session"]["institution"],
        lab=cfg["session"]["lab"],
    )
    behavior = nwbfile.create_processing_module(name="behavior", description="Tracking and vocalization annotations")
    annotation_rows = []
    offset = 0.0
    audio_layout = [_audio_shape(chunk) for chunk in chunks]
    audio_samples = sum(item[0] for item in audio_layout)
    audio_channels = audio_layout[0][1]
    audio_rate = audio_layout[0][2]
    audio_dtype = audio_layout[0][3]
    if any(item[1:] != (audio_channels, audio_rate, audio_dtype) for item in audio_layout):
        raise ValueError("Audio channel count or sampling rate changes between chunks")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_audio_path = output_path.with_suffix(".audio.tmp")
    audio_data = numpy.memmap(temporary_audio_path, dtype=audio_dtype, mode="w+", shape=(audio_samples, audio_channels))
    video_paths = []
    video_info = []
    tracking_paths = []
    skipped_annotations = 0
    audio_cursor = 0
    for chunk in chunks:
        audio_chunk, rate = _read_audio_chunk(chunk)
        audio_data[audio_cursor : audio_cursor + len(audio_chunk)] = audio_chunk
        chunk_videos = sorted(chunk.glob("*.mp4"))
        if len(chunk_videos) != 1:
            raise ValueError(f"Expected one MP4 in {chunk}, found {chunk_videos}")
        video_paths.append(chunk_videos[0])
        video_info.append(_video_info(chunk_videos[0]))
        tracking_paths.extend(sorted(chunk.glob("*.tracks.csv")))
        for annotation_path in sorted(chunk.glob("*_annotations.csv")):
            with annotation_path.open(newline="") as stream:
                for row in csv.DictReader(stream):
                    if not row["start_seconds"].strip() or not row["stop_seconds"].strip():
                        skipped_annotations += 1
                        continue
                    annotation_rows.append(
                        {
                            **row,
                            "start_seconds": float(row["start_seconds"]) + offset,
                            "stop_seconds": float(row["stop_seconds"]) + offset,
                        }
                    )
        offset += len(audio_chunk) / rate
        audio_cursor += len(audio_chunk)
    nwbfile.add_acquisition(
        ndx_sound.AcousticWaveformSeries(
            name="Multi-channel Acoustic Data",
            data=audio_data,
            rate=float(rate),
            unit="audio",
            description=cfg["audio"]["description"],
        )
    )
    audio_data.flush()
    combined_video = output_path.with_name("combined_behavior.mp4")
    _concatenate_videos(video_paths, combined_video)
    video_rate = video_info[0][1]
    total_frames = sum(frame_count for frame_count, _ in video_info)
    nwbfile.add_acquisition(
        pynwb.image.ImageSeries(
            name="External Behavioral Video (Combined)",
            unit="n/a",
            starting_time=0.0,
            rate=float(video_rate),
            external_file=[combined_video.name],
            format="external",
            description=cfg["video"]["description"],
        )
    )
    tracks = _add_tracking(behavior, tracking_paths)
    session_label = f"experiment{experiment_dir.name.split('_')[-1]}"
    track_nwbs = _write_track_nwbs(
        tracking_paths=tracking_paths,
        output_dir=output_path.parent,
        session_label=session_label,
        session_start=_session_start(experiment_dir),
        cfg=cfg,
    )
    subjects_table = ndx_multisubjects.SubjectsTable(description="Animals tracked in this session")
    for track, track_path in track_nwbs:
        subjects_table.add_row(
            species=cfg["subject"]["species"],
            subject_id=sanitize_label(track) or "unknown",
            sex=cfg["subject"]["sex"],
            age=cfg["subject"]["age"],
            individual_subj_link=track_path.name,
        )
    nwbfile.subjects_table = subjects_table
    events = EventsTable(name="vocalizations", description="Vocalization events with onset timestamps and durations")
    events.add_column(name="label", description="Vocalization annotation label.")
    events.add_column(name="channel", description="Microphone channel.")
    events.add_column(name="duration_seconds", description="Vocalization duration in seconds.")
    for row in annotation_rows:
        events.add_event(
            timestamp=row["start_seconds"],
            label=row["name"],
            channel=row["channel"],
            duration_seconds=row["stop_seconds"] - row["start_seconds"],
        )
    behavior.add(events)
    if skipped_annotations:
        print(f"Skipped {skipped_annotations} incomplete annotation row(s) in {experiment_dir}")
    backend_configuration = get_default_backend_configuration(nwbfile, backend="hdf5")
    backend_configuration.apply_global_compression(
        compression_method="gzip", compression_options={"compression_opts": 4}
    )
    with NWBHDF5IO(output_path, "w") as io:
        io.write(nwbfile)
    del audio_data
    temporary_audio_path.unlink()


def load_config(path, /):
    return yaml.safe_load(path.read_text())
