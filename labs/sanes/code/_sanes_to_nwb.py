#!/usr/bin/env python3
"""
_sanes_to_nwb.py
================================
Original conversion developed by Neha Thomas (neha-thomas477) as the Jupyter
notebook ``sanesDatatoNWB_v2.ipynb``, which is committed verbatim next to this
file.

This module is that notebook transcribed into a callable function, cell by
cell and in the same order. The conversion logic is unchanged: the same
readers, the same concatenation, the same names, the same assumptions, and the
same rough edges (listed in ``../README.md``). What changed is only what a
notebook cannot carry: the hard-coded input and output paths became arguments,
and the values the notebook wrote as literals moved into ``config.yaml``. The
notebook's one-off "combine every video into one mp4" cell is deliberately not
transcribed, since the notebook itself marks it as run once ever by hand.

One session is one folder holding the ``idx_*`` recording chunks::

    <session>/
      idx_0/
        *.wav             one file per audio channel ("multichannel" ones skipped)
        *.mp4             the behavioral video for this chunk
        *.slp             SLEAP pose estimation
        *annotations.csv  vocalization annotations (start_seconds, stop_seconds, ...)
      idx_1/
        ...

A chunk carries exactly one annotations table. Most name it
``annotations.csv``, some name it after the channel and chunk instead, as in
``channel_0_4_annotations.csv``. Both namings occur within one upload.

The chunks are stitched into one NWB file: audio channels are read per chunk
and concatenated end to end, vocalization annotation times are offset by the
cumulative video duration before them, and each chunk's video is one entry of a
single external-file ``ImageSeries``.

``batch_convert.py`` is what dispatch runs. It loops this module's
:pyfunc:`build_nwb` over the session folders in an incoming dandiset.
"""

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import dateutil.tz
import hdmf.common
import natsort
import numpy
import pandas
import pynwb
import scipy.io.wavfile
import yaml
from neuroconv.datainterfaces import SLEAPInterface

SESSION_START_TIME_FORMAT = "%Y-%m-%d%H:%M:%S%z"


def load_cfg(config_path, /):
    with open(config_path, "r") as file:
        cfg = yaml.safe_load(file)
    return cfg


def get_video_info_ffprobe(video_path, /):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=duration,nb_frames,r_frame_rate",
        "-of",
        "json",
        video_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    info = json.loads(result.stdout)

    stream = info["streams"][0]
    duration = float(stream.get("duration", 0))
    frame_count = int(stream.get("nb_frames", 0))
    return duration, frame_count


def find_annotations_file(folder_path, /):
    """The chunk's vocalization annotations, whatever it is named.

    Most chunks name it ``annotations.csv``, but some carry the channel and
    chunk in the name instead (``channel_0_4_annotations.csv``). Both are
    valid uploads holding the same per-chunk table, so match on the suffix
    the way the ``.wav``/``.mp4``/``.slp`` lookups below do.
    """
    folder_path = Path(folder_path)
    matches = natsort.natsorted(f for f in os.listdir(folder_path) if f.endswith("annotations.csv"))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one *annotations.csv in {folder_path}, found {len(matches)}: {matches}")
    annotations_path = folder_path / matches[0]
    return annotations_path


def session_start_time(cfg, /):
    """The configured start time, or now, which is what the notebook used."""
    configured = cfg["session"].get("start_time", "")
    if not configured:
        start_time = datetime.now(dateutil.tz.tzlocal())
        return start_time
    start_time = datetime.strptime(configured, SESSION_START_TIME_FORMAT)
    return start_time


def build_nwb(*, input_folder, out_nwb, cfg):
    """Convert one session folder of ``idx_*`` chunks into a single NWB file."""
    input_folder = Path(input_folder)
    out_nwb = Path(out_nwb)

    folders = [f for f in os.listdir(input_folder) if os.path.isdir(input_folder / f) and f.startswith("idx_")]
    folders = natsort.natsorted(folders)
    if not folders:
        raise ValueError(f"No idx_* chunk folders found in {input_folder}")

    nwbfile = pynwb.NWBFile(
        session_description=cfg["session"]["description"],
        identifier=cfg["session"]["identifier"],
        session_start_time=session_start_time(cfg),
    )

    audiochannel_data = []
    vid_files = []
    vox_data = []
    cumulative_offset = 0.0
    vidStartFrames = [cumulative_offset]

    for folder in folders:
        folder_path = input_folder / folder
        wav_files = [f for f in os.listdir(folder_path) if f.endswith(".wav") and "multichannel" not in f]
        wav_files = natsort.natsorted(wav_files)

        channel_columns = []
        for wav_file in wav_files:
            audio_sampling_rate, thisData = scipy.io.wavfile.read(folder_path / wav_file)
            thisData = thisData.reshape(-1, 1)
            channel_columns.append(thisData)

        data = numpy.hstack(channel_columns)
        audiochannel_data.append(data)

        vid_file = [f for f in os.listdir(folder_path) if f.endswith(".mp4")][0]
        vid_path = folder_path / vid_file
        duration, frame_count = get_video_info_ffprobe(str(vid_path))
        print(f"Video: {vid_file}, Duration: {duration} seconds, Frame Count: {frame_count}")
        vid_files.append(vid_path)

        annotationsPath = find_annotations_file(folder_path)
        df = pandas.read_csv(annotationsPath)
        df.start_seconds = df.start_seconds + cumulative_offset
        df.stop_seconds = df.stop_seconds + cumulative_offset
        vox_data.append(df)
        cumulative_offset += duration
        vidStartFrames.append(frame_count + vidStartFrames[-1])

        slp_files = [f for f in os.listdir(folder_path) if f.endswith(".slp")]
        slp_path = folder_path / slp_files[0]
        interface = SLEAPInterface(file_path=str(slp_path), verbose=False)
        metadata = interface.get_metadata()
        interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata)

    print(vidStartFrames)

    multichannel_data = numpy.concatenate(audiochannel_data, axis=0)

    acoustic_waveform_series = pynwb.TimeSeries(
        name=cfg["acoustic"]["name"],
        description=cfg["acoustic"]["description"],
        data=multichannel_data,
        rate=float(audio_sampling_rate),
        starting_time=0.0,
        unit=cfg["acoustic"]["unit"],
    )
    nwbfile.add_acquisition(acoustic_waveform_series)

    externalFile = [os.path.relpath(f, out_nwb.parent) for f in vid_files]
    print(externalFile)
    sampling_rate = float(cfg["video"]["rate"])

    extBehVideos = pynwb.image.ImageSeries(
        name=cfg["video"]["name"],
        unit=cfg["video"]["unit"],
        starting_time=0.0,
        starting_frame=vidStartFrames[:-1],
        rate=sampling_rate,
        description=cfg["video"]["description"],
        external_file=externalFile,
        format="external",
    )
    nwbfile.add_acquisition(extBehVideos)

    behaviorModule = nwbfile.get_processing_module("behavior")
    all_vox_df = pandas.concat(vox_data, ignore_index=True)
    all_vox_df = all_vox_df.rename(
        columns={
            "start_seconds": "start_time",
            "stop_seconds": "stop_time",
            "name": "label",
        }
    )
    vocalizations_table = pynwb.epoch.TimeIntervals.from_dataframe(
        name=cfg["vocalizations"]["name"],
        df=all_vox_df,
    )
    behaviorModule.add_container(vocalizations_table)

    subject = pynwb.file.Subject(
        subject_id=cfg["subject"]["id"],
        description=cfg["subject"]["description"],
        species=cfg["subject"]["species"],
        age=cfg["subject"]["age"],
        sex=cfg["subject"]["sex"],
    )
    nwbfile.subject = subject

    subjectTable = hdmf.common.DynamicTable(
        name=cfg["subject_table"]["name"],
        description=cfg["subject_table"]["description"],
    )
    subjectTable.add_column("subject_id", "Unique subject ID")
    subjectTable.add_column("age", "Age")
    subjectTable.add_column("species", "Species")
    subjectTable.add_column("sex", "Sex")
    for row in cfg["subject_table"]["rows"]:
        subjectTable.add_row(
            subject_id=row["subject_id"],
            age=row["age"],
            species=row["species"],
            sex=row["sex"],
        )

    general_module = nwbfile.create_processing_module(name="general", description="general metadata about multisubject")
    general_module.add(subjectTable)

    with pynwb.NWBHDF5IO(str(out_nwb), "w") as io:
        io.write(nwbfile)
        print(f"NWB file saved to {out_nwb}")

    return out_nwb


def parse_args():
    parser = argparse.ArgumentParser(description="Convert one Sanes session folder of idx_* chunks to NWB")
    parser.add_argument("--input", required=True, type=Path, help="Session folder holding the idx_* chunk folders")
    parser.add_argument("--out", required=True, type=Path, help="Output .nwb file path")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.yaml",
        help="YAML config (default: config.yaml next to this script)",
    )
    arguments = parser.parse_args()
    return arguments


def main():
    args = parse_args()
    cfg = load_cfg(args.config)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    build_nwb(input_folder=args.input, out_nwb=args.out, cfg=cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
