"""Convert one SSA GT experiment into a multisubject NWB file plus one NWB file per tracked animal."""

import csv
import datetime
import json
import os
import re
import subprocess
import tempfile

import ndx_multisubjects
import ndx_sound
import neuroconv.tools.nwb_helpers
import numpy
import pynwb
import pynwb.event
import pynwb.file
import pynwb.image
import scipy.io.wavfile
import yaml


def sanitize_label(text, /):
    return re.sub(r"[^0-9A-Za-z]", "", text)


def _float_or_nan(value, /):
    return float(value) if value and value.strip() else numpy.nan


def _chunk_audio_layout(chunk, /):
    paths = sorted(chunk.glob("channel_*_*.wav"))
    if not paths:
        raise ValueError(f"No channel WAV files found in {chunk}")
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


def _session_start(experiment_dir, /):
    logs = sorted(experiment_dir.glob("*log_*.txt"))
    if len(logs) != 1:
        raise ValueError(f"Expected one experiment log in {experiment_dir}, found {logs}")
    for line in logs[0].read_text().splitlines():
        match = re.match(r"(?P<timestamp>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})>Started Experiment Now", line)
        if match:
            start = datetime.datetime.strptime(match["timestamp"], "%Y-%m-%d_%H-%M-%S")
            return start.replace(tzinfo=datetime.timezone.utc)
    raise ValueError(f"No 'Started Experiment Now' entry found in {logs[0]}")


def _experiment_metadata(*, experiment_dir, config_path, cfg):
    selected = {}
    metadata_name = cfg.get("experiment_metadata")
    if metadata_name is None:
        return selected
    metadata = yaml.safe_load((config_path.parent / metadata_name).read_text())
    experiment_number = int(experiment_dir.name.split("_")[-1])
    selected.update(metadata["default"])
    for candidate in metadata["ranges"]:
        start, end = candidate["experiments"]
        if start <= experiment_number <= end:
            selected.update(candidate)
            break
    return selected


def _tracking_series(*, name, rows, description):
    series = pynwb.TimeSeries(
        name=name,
        data=numpy.asarray(
            [[_float_or_nan(row.get("nose.x", "")), _float_or_nan(row.get("nose.y", ""))] for row in rows]
        ),
        unit="pixels",
        timestamps=numpy.asarray([row["timestamp"] for row in rows]),
        description=description,
    )
    return series


def _write_nwbfile(*, nwbfile, path):
    backend_configuration = neuroconv.tools.nwb_helpers.get_default_backend_configuration(nwbfile, backend="hdf5")
    backend_configuration.apply_global_compression(["gzip"], [{"level": 4}])
    neuroconv.tools.nwb_helpers.configure_backend(nwbfile=nwbfile, backend_configuration=backend_configuration)
    with pynwb.NWBHDF5IO(path, "w") as io:
        io.write(nwbfile)


def _write_track_nwbs(*, track_rows, output_dir, session_label, session_start, cfg):
    written = []
    for track_index, (track, rows) in enumerate(sorted(track_rows.items())):
        subject_label = f"{track_index:02d}"
        track_path = output_dir / f"sub-{subject_label}" / f"sub-{subject_label}_ses-{session_label}.nwb"
        track_nwb = pynwb.NWBFile(
            session_description=f"Tracking data for {track}",
            identifier=f"sanes-{cfg['session']['dataset']}-{session_label}-track-{subject_label}",
            session_start_time=session_start,
            experimenter=cfg["session"]["experimenter"],
            institution=cfg["session"]["institution"],
            lab=cfg["session"]["lab"],
            subject=pynwb.file.Subject(
                subject_id=subject_label,
                description=f"Animal tracked as '{track}' in this experiment.",
                species=cfg["subject"]["species"],
                sex=cfg["subject"]["sex"],
                age=cfg["subject"]["age"],
            ),
        )
        behavior = track_nwb.create_processing_module(name="behavior", description="Tracking annotations")
        behavior.add(
            _tracking_series(
                name="tracking",
                rows=rows,
                description="Nose x/y tracking for this animal. The source CSV holds all landmarks and scores.",
            )
        )
        track_path.parent.mkdir(parents=True, exist_ok=True)
        _write_nwbfile(nwbfile=track_nwb, path=track_path)
        written.append((subject_label, track_path))
    return written


def build_nwb(*, experiment_dir, output_path, config_path):
    cfg = yaml.safe_load(config_path.read_text())
    experiment_metadata = _experiment_metadata(experiment_dir=experiment_dir, config_path=config_path, cfg=cfg)
    chunks = sorted(experiment_dir.glob("idx_*"), key=lambda path: int(path.name.split("_")[-1]))
    if not chunks:
        raise ValueError(f"No idx_* chunks found under {experiment_dir}")
    session_label = f"experiment{experiment_dir.name.split('_')[-1]}"
    session_start = _session_start(experiment_dir)
    nwbfile = ndx_multisubjects.NdxMultiSubjectsNWBFile(
        session_description=experiment_metadata.get("description", cfg["session"]["description"]),
        identifier=f"sanes-{cfg['session']['dataset']}-{experiment_dir.name}",
        session_start_time=session_start,
        experimenter=cfg["session"]["experimenter"],
        institution=cfg["session"]["institution"],
        lab=cfg["session"]["lab"],
    )

    audio_layout = [_chunk_audio_layout(chunk) for chunk in chunks]
    audio_channels = len(audio_layout[0]["paths"])
    audio_rate = audio_layout[0]["rate"]
    audio_dtype = audio_layout[0]["dtype"]
    if any(
        (len(item["paths"]), item["rate"], item["dtype"]) != (audio_channels, audio_rate, audio_dtype)
        for item in audio_layout
    ):
        raise ValueError(
            f"Audio channel count, sampling rate, or sample type changes between chunks of {experiment_dir}"
        )
    audio_samples = sum(item["samples"] for item in audio_layout)

    video_paths = []
    for chunk in chunks:
        chunk_videos = sorted(chunk.glob("*.mp4"))
        if len(chunk_videos) != 1:
            raise ValueError(f"Expected one MP4 in {chunk}, found {chunk_videos}")
        video_paths.append(chunk_videos[0])
    video_info = [_video_info(path) for path in video_paths]
    video_rate = video_info[0][1]
    if any(rate != video_rate for _, rate in video_info):
        raise ValueError(f"Video frame rate changes between chunks of {experiment_dir}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_audio_path = output_path.with_suffix(".audio.tmp")
    audio_data = numpy.memmap(temporary_audio_path, dtype=audio_dtype, mode="w+", shape=(audio_samples, audio_channels))
    try:
        annotation_rows = []
        skipped_annotations = 0
        track_rows = {}
        audio_cursor = 0
        frame_cursor = 0
        for chunk, layout, (frame_count, _) in zip(chunks, audio_layout, video_info):
            for channel_index, path in enumerate(layout["paths"]):
                _, data = scipy.io.wavfile.read(path, mmap=True)
                audio_data[audio_cursor : audio_cursor + layout["samples"], channel_index] = data
            audio_offset = audio_cursor / audio_rate
            for annotation_path in sorted(chunk.glob("*_annotations.csv")):
                with annotation_path.open(newline="") as stream:
                    for row in csv.DictReader(stream):
                        if not row["start_seconds"].strip() or not row["stop_seconds"].strip():
                            skipped_annotations += 1
                            continue
                        start = float(row["start_seconds"]) + audio_offset
                        stop = float(row["stop_seconds"]) + audio_offset
                        annotation_rows.append(
                            {"name": row["name"], "channel": row["channel"], "start": start, "stop": stop}
                        )
            # Tracking frame indices count frames of this chunk's video, so they are placed on the
            # concatenated video's clock, the same clock the combined ImageSeries uses.
            for tracking_path in sorted(chunk.glob("*.tracks.csv")):
                with tracking_path.open(newline="") as stream:
                    for row in csv.DictReader(stream):
                        timestamp = (frame_cursor + int(float(row["frame_idx"]))) / video_rate
                        track_rows.setdefault(row["track"], []).append({**row, "timestamp": timestamp})
            audio_cursor += layout["samples"]
            frame_cursor += frame_count
        audio_data.flush()

        nwbfile.add_acquisition(
            ndx_sound.AcousticWaveformSeries(
                name="Multi-channel Acoustic Data",
                data=audio_data,
                rate=float(audio_rate),
                description=cfg["audio"]["description"],
            )
        )

        combined_video = output_path.with_name(f"sub-multi_ses-{session_label}_video.mp4")
        _concatenate_videos(paths=video_paths, output_path=combined_video)
        nwbfile.add_acquisition(
            pynwb.image.ImageSeries(
                name="External Behavioral Video (Combined)",
                unit="n/a",
                starting_time=0.0,
                rate=float(video_rate),
                external_file=[combined_video.name],
                starting_frame=[0],
                format="external",
                num_samples=frame_cursor,
                description=cfg["video"]["description"],
            )
        )

        behavior = nwbfile.create_processing_module(
            name="behavior", description="Tracking and vocalization annotations"
        )
        for track, rows in sorted(track_rows.items()):
            behavior.add(
                _tracking_series(
                    name=f"tracking_{sanitize_label(track) or 'unknown'}",
                    rows=rows,
                    description="Nose x/y tracking from annotation CSV. The source CSV holds all landmarks and scores.",
                )
            )

        track_nwbs = _write_track_nwbs(
            track_rows=track_rows,
            output_dir=output_path.parent.parent,
            session_label=session_label,
            session_start=session_start,
            cfg=cfg,
        )
        if track_nwbs:
            subjects_table = ndx_multisubjects.SubjectsTable(description="Animals tracked in this session")
            for subject_label, track_path in track_nwbs:
                subjects_table.add_row(
                    species=cfg["subject"]["species"],
                    subject_id=subject_label,
                    sex=cfg["subject"]["sex"],
                    age=cfg["subject"]["age"],
                    individual_subj_link=os.path.relpath(track_path, output_path.parent),
                )
            nwbfile.subjects_table = subjects_table

        if annotation_rows:
            events = pynwb.event.EventsTable(
                name="vocalizations",
                description="Vocalization onsets with durations, offset onto the concatenated audio clock.",
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
            print(f"Skipped {skipped_annotations} incomplete annotation row(s) in {experiment_dir}")

        _write_nwbfile(nwbfile=nwbfile, path=output_path)
    finally:
        del audio_data
        temporary_audio_path.unlink(missing_ok=True)
