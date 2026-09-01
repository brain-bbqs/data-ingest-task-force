#!/usr/bin/env python3
"""
_sanes_to_nwb.py
================================
Original conversion developed by Neha Thomas (neha-thomas477) as three v2
scripts, committed verbatim next to this file: ``concat_sanes_data.py``,
``sanes_multisubject_to_nwb.py`` and ``sanes_individual_subject_to_nwb.py``.
Those supersede the v1 notebook (``sanesDatatoNWB_v2.ipynb``) this module used
to be a transcription of; the notebook is retired from the tree (see git
history and ``../README.md``).

This module is the v2 scripts transcribed into callable functions, following
the same order and logic. What changed is only what the scripts' own
hard-coded paths and literals cannot carry as a library: the input, output and
config paths became arguments, and per-track output paths are threaded through
explicitly instead of assumed by convention (see ``build_multisubject_nwb``'s
docstring). ``sanes_individual_subject_to_nwb.py`` is not transcribed here at
all; its intent (attaching a per-track ``Subject`` to a per-track NWB file) is
already accomplished, more correctly, by stage 1 below writing ``subject=``
directly. See ``../README.md`` for the full reasoning.

One session is one folder holding the ``idx_*`` recording chunks::

    <session>/
      idx_0/
        *.wav             one file per audio channel ("multichannel" ones skipped)
        *.mp4             the behavioral video for this chunk
        *.slp             SLEAP pose estimation (a chunk may hold more than one)
        annotations.csv   vocalization annotations (start_seconds, stop_seconds, ...)
      idx_1/
        ...

The pipeline runs in three stages, matching the three v2 scripts:

1. ``write_per_track_nwbs`` (from ``concat_sanes_data.py``): merge every
   chunk's ``.slp`` file into one SLEAP ``Labels`` object, split it by track,
   and write one NWB per track under ``Split_SLPs/``, each carrying that
   track's pose data and a ``pynwb.file.Subject`` built from ``config.yaml``.
2. ``concat_video_files`` (also from ``concat_sanes_data.py``): concatenate
   every chunk's ``.mp4`` into one ``combined_output.mp4`` via ffmpeg.
3. ``build_multisubject_nwb`` (from ``sanes_multisubject_to_nwb.py``): build
   the top-level session NWB using ``ndx_multisubjects``, linking each
   subject row to its stage-1 per-track NWB, holding the concatenated
   multichannel audio as an ``ndx_sound.AcousticWaveformSeries``, one
   ``ImageSeries`` per chunk video plus one for the combined video, and a
   ``vocalizations`` ``TimeIntervals`` table.

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
import ffmpeg
import natsort
import ndx_multisubjects
import ndx_sound
import neuroconv.tools.nwb_helpers
import numpy
import pandas
import pynwb
import scipy.io.wavfile
import sleap_io
import sleap_io.model.matching
import yaml

SESSION_START_TIME_FORMAT = "%Y-%m-%d%H:%M:%S%z"
SPLIT_SLP_SUBDIRECTORY = "Split_SLPs"
COMBINED_VIDEO_NAME = "combined_output.mp4"
MULTISUBJECT_NWB_NAME = "sanes_multisubject_1.nwb"


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


def session_start_time(cfg, /):
    """The configured start time, or now, matching what the v2 scripts do
    whenever their own config's ``session.start_time`` is left blank."""
    configured = cfg["session"].get("start_time", "")
    if not configured:
        start_time = datetime.now(dateutil.tz.tzlocal())
        return start_time
    start_time = datetime.strptime(configured, SESSION_START_TIME_FORMAT)
    return start_time


def discover_chunk_folders(input_folder, /):
    input_folder = Path(input_folder)
    folders = [f for f in input_folder.iterdir() if f.is_dir() and f.name.startswith("idx_")]
    return natsort.natsorted(folders)


def chunk_video_path(chunk_folder, /):
    """The one behavioral video a chunk carries."""
    chunk_folder = Path(chunk_folder)
    vid_files = [f for f in os.listdir(chunk_folder) if f.endswith(".mp4")]
    return chunk_folder / vid_files[0]


def merge_chunk_sleap_labels(chunk_folders, /):
    """Merge every chunk's ``.slp`` file(s) into one SLEAP ``Labels``.

    Matches ``concat_sanes_data.get_slp_files``: every ``.slp`` across every
    chunk is collected and natsorted together (a chunk is not restricted to
    exactly one, unlike the plain-video/annotations lookups elsewhere), the
    first is the merge base, and the rest are merged in by exact video path.
    """
    slp_files = natsort.natsorted(str(slp) for folder in chunk_folders for slp in Path(folder).glob("*.slp"))
    if not slp_files:
        raise ValueError(f"No .slp files found under {[str(f) for f in chunk_folders]}")

    base_labels = sleap_io.load_file(slp_files[0])
    for slp_path in slp_files[1:]:
        labels_new = sleap_io.load_file(slp_path)
        base_labels.merge(
            labels_new, video_matcher=sleap_io.model.matching.PATH_VIDEO_MATCHER, frame_strategy="keep_both"
        )
    return base_labels


def split_labels_by_track(base_labels, /):
    """One SLEAP ``Labels`` object per track, holding only that track's frames."""
    track_labels_list = []
    for track in base_labels.tracks:
        lf_sub = []
        for labeled_frame in base_labels.labeled_frames:
            instances = [instance for instance in labeled_frame.instances if instance.track == track]
            if instances:
                new_labeled_frame = labeled_frame.__class__(
                    video=labeled_frame.video, frame_idx=labeled_frame.frame_idx, instances=instances
                )
                lf_sub.append(new_labeled_frame)

        track_labels = sleap_io.Labels(
            labeled_frames=lf_sub,
            videos=base_labels.videos,
            skeletons=base_labels.skeletons,
            tracks=[track],
        )
        track_labels_list.append(track_labels)
    return track_labels_list


def write_per_track_nwbs(*, track_labels_list, out_dir, cfg, session_start, experimenter, institution):
    """Save each track's ``Labels`` as its own ``.slp`` and write an NWB per
    track carrying that track's pose data plus a ``Subject`` from *cfg*.

    Track index N in *track_labels_list* is read against ``config.yaml``'s
    ``subject_N`` block, matching ``concat_sanes_data.create_merged_slp_tracks``.

    Returns the ``(track_name, nwb_path)`` pairs in creation order, which
    ``build_multisubject_nwb`` links to by that same index rather than by the
    hard-coded ``sub-00/track_0.nwb``-style paths the original
    ``sanes_multisubject_to_nwb.py`` assumes (see that function's docstring).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for track_index, track_labels in enumerate(track_labels_list):
        track_name = track_labels.tracks[0].name or f"track_{track_labels.tracks[0].id}"
        slp_path = out_dir / f"{track_name}.slp"
        nwb_path = out_dir / f"{track_name}.nwb"

        track_labels.save(str(slp_path))
        if nwb_path.exists():
            nwb_path.unlink()

        subject_key = f"subject_{track_index}"
        subject = pynwb.file.Subject(
            subject_id=cfg[subject_key]["id"],
            species=cfg[subject_key]["species"],
            sex=cfg[subject_key]["sex"],
            age=cfg[subject_key]["age"],
            description=cfg[subject_key]["description"],
        )
        identifier = f"Subject_{subject.subject_id}"
        session_description = f"SLEAP tracking data for {subject.subject_id}"

        sleap_io.io.nwb.write_nwb(
            track_labels,
            str(nwb_path),
            nwb_file_kwargs={
                "session_description": session_description,
                "identifier": identifier,
                "session_start_time": session_start,
                "experimenter": experimenter,
                "institution": institution,
                "subject": subject,
            },
        )
        written.append((track_name, nwb_path))
    return written


def concat_video_files(*, chunk_folders, combined_output):
    """Concatenate every chunk's ``.mp4`` into one file via ffmpeg.

    Matches ``concat_sanes_data.concat_video_files``: each chunk video is
    first transcoded to an intermediate ``.ts`` file next to the original
    (inside the *incoming* session folder, not the output directory -- ported
    as-is, see ``../README.md``), the ``.ts`` files are concatenated, and the
    intermediates are removed afterward.
    """
    combined_output = Path(combined_output)

    ts_files = []
    for chunk_folder in chunk_folders:
        vid_path = chunk_video_path(chunk_folder)
        ts_file = vid_path.with_suffix(".ts")
        ffmpeg.input(str(vid_path)).output(str(ts_file), format="mpegts", vcodec="copy", acodec="copy").run(
            overwrite_output=True, quiet=True
        )
        ts_files.append(ts_file)

    concat_str = "|".join(str(f) for f in ts_files)
    ffmpeg.input(f"concat:{concat_str}", format="mpegts").output(
        str(combined_output), vcodec="copy", acodec="copy"
    ).run(overwrite_output=True, quiet=True)

    for ts_file in ts_files:
        ts_file.unlink()
    return combined_output


def read_chunk_audio(chunk_folder, /):
    """One chunk's audio channels, stacked into a ``(samples, channels)`` array."""
    chunk_folder = Path(chunk_folder)
    wav_files = natsort.natsorted(f for f in os.listdir(chunk_folder) if f.endswith(".wav") and "multichannel" not in f)

    channel_columns = []
    sampling_rate = None
    for wav_file in wav_files:
        sampling_rate, this_data = scipy.io.wavfile.read(chunk_folder / wav_file)
        channel_columns.append(this_data.reshape(-1, 1))
    return numpy.hstack(channel_columns), sampling_rate


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


def read_chunk_annotations(chunk_folder, *, cumulative_offset):
    """One chunk's vocalization annotations, offset by *cumulative_offset*.

    Restores this module's own v1-era ``find_annotations_file`` lookup
    (dropped when the v2 scripts were ported in for hard-coding
    ``annotations.csv`` exactly): a real chunk in 000522/experiment_135
    (``idx_4``) names its table ``channel_0_4_annotations.csv`` instead, which
    otherwise breaks the whole session's conversion. See ``../README.md``.
    """
    annotations_path = find_annotations_file(chunk_folder)
    df = pandas.read_csv(annotations_path)
    df.start_seconds = df.start_seconds + cumulative_offset
    df.stop_seconds = df.stop_seconds + cumulative_offset
    return df


def build_multisubject_nwb(*, input_folder, track_nwbs, combined_video, out_nwb, cfg, session_start):
    """Build the top-level session NWB, linking each subject row to its
    stage-1 per-track NWB.

    *track_nwbs* is the ``(track_name, nwb_path)`` list ``write_per_track_nwbs``
    returned; track index N is linked against ``config.yaml``'s ``subject_N``
    block by that same creation-order index. The original
    ``sanes_multisubject_to_nwb.py`` instead hard-codes the three link paths
    (``sub-00/track_0.nwb``, ``sub-01/track_1.nwb``, ``sub-02/track_2.nwb``),
    which do not match what ``concat_sanes_data.py`` actually writes (no
    ``sub-NN/`` folder, and the track name need not be ``track_N``). Linking
    to the paths stage 1 actually returned is the straightforward path fix
    this port makes to run at all; see ``../README.md``.
    """
    input_folder = Path(input_folder)
    out_nwb = Path(out_nwb)
    chunk_folders = discover_chunk_folders(input_folder)
    if not chunk_folders:
        raise ValueError(f"No idx_* chunk folders found in {input_folder}")

    nwbfile = ndx_multisubjects.NdxMultiSubjectsNWBFile(
        session_description=cfg["session"]["description"],
        identifier="Sanes-Multisubject-1",
        session_start_time=session_start,
        experimenter=cfg["session"]["experimenter"],
        institution=cfg["session"]["institution"],
    )

    subjects_table = ndx_multisubjects.SubjectsTable(description="Subjects in this session")
    for track_index, (_track_name, track_nwb_path) in enumerate(track_nwbs):
        subject_key = f"subject_{track_index}"
        link = os.path.relpath(str(track_nwb_path), os.path.dirname(out_nwb))
        subjects_table.add_row(
            species=cfg[subject_key]["species"],
            subject_id=cfg[subject_key]["id"],
            age=cfg[subject_key]["age"],
            sex=cfg[subject_key]["sex"],
            individual_subj_link=link,
        )
    nwbfile.subjects_table = subjects_table

    audiochannel_data = []
    vid_files = []
    vox_data = []
    cumulative_offset = 0.0
    vid_start_frames = [cumulative_offset]
    audio_sampling_rate = None

    for chunk_folder in chunk_folders:
        data, sampling_rate = read_chunk_audio(chunk_folder)
        audiochannel_data.append(data)
        audio_sampling_rate = sampling_rate

        vid_path = chunk_video_path(chunk_folder)
        duration, frame_count = get_video_info_ffprobe(str(vid_path))
        vid_files.append(vid_path)

        vox_data.append(read_chunk_annotations(chunk_folder, cumulative_offset=cumulative_offset))
        cumulative_offset += duration
        vid_start_frames.append(frame_count + vid_start_frames[-1])

    multichannel_data = numpy.concatenate(audiochannel_data, axis=0)
    acoustic_waveform_series = ndx_sound.AcousticWaveformSeries(
        name="Multi-channel Acoustic Data",
        description=cfg["acousticwaveformseries"]["multichannel_audio"]["description"],
        data=multichannel_data,
        rate=float(audio_sampling_rate),
    )
    nwbfile.add_acquisition(acoustic_waveform_series)

    # pynwb >=3.2 requires num_samples on an external-file ImageSeries that
    # times itself with rate= rather than data length, which is exactly this
    # series' shape. The original script (targeting pynwb<3.2, per v1's
    # rough edges) never sets it. total_frame_count is already computed above
    # for starting_frame, so supplying it is a straightforward fix to run
    # against an unbounded, modern pynwb rather than a change to the data;
    # see ../README.md.
    total_frame_count = int(vid_start_frames[-1])

    video_cfg = cfg["imageseries"]["behavioral_video"]
    per_chunk_external_file = [os.path.relpath(str(f), os.path.dirname(out_nwb)) for f in vid_files]
    per_chunk_videos = pynwb.image.ImageSeries(
        name="External Behavioral Videos",
        unit=video_cfg["unit"],
        starting_time=0.0,
        starting_frame=numpy.asarray(vid_start_frames[:-1], dtype=numpy.int64),
        rate=float(video_cfg["rate"]),
        description=video_cfg["description"],
        external_file=per_chunk_external_file,
        format="external",
        num_samples=total_frame_count,
    )
    nwbfile.add_acquisition(per_chunk_videos)

    behavior_module = nwbfile.create_processing_module(name="behavior", description="Vocalization annotations")
    all_vox_df = pandas.concat(vox_data, ignore_index=True)
    all_vox_df = all_vox_df.rename(
        columns={"start_seconds": "start_time", "stop_seconds": "stop_time", "name": "label"}
    )
    vocalizations_table = pynwb.epoch.TimeIntervals.from_dataframe(
        name="vocalizations",
        df=all_vox_df,
    )
    behavior_module.add(vocalizations_table)

    combined_external_file = [os.path.relpath(str(combined_video), os.path.dirname(out_nwb))]
    combined_video_series = pynwb.image.ImageSeries(
        name="External Behavioral Video (Combined)",
        unit=video_cfg["unit"],
        starting_time=0.0,
        rate=float(video_cfg["rate"]),
        description=video_cfg["description"],
        external_file=combined_external_file,
        format="external",
        num_samples=total_frame_count,
    )
    nwbfile.add_acquisition(combined_video_series)

    # The original sanes_multisubject_to_nwb.py computes a gzip backend
    # configuration and then writes with a plain NWBHDF5IO write, never
    # actually applying it (configure_and_write_nwbfile is imported but
    # unused there too). Ported as-is: the configuration below is computed
    # and discarded, matching that behavior rather than the evident intent.
    # See ../README.md's "Known rough edges".
    backend_configuration = neuroconv.tools.nwb_helpers.get_default_backend_configuration(nwbfile, backend="hdf5")
    backend_configuration.apply_global_compression(
        compression_method="gzip",
        compression_options={"compression_opts": 4},
    )

    with pynwb.NWBHDF5IO(str(out_nwb), "w") as io:
        io.write(nwbfile)

    return out_nwb


def build_nwb(*, input_folder, out_dir, cfg):
    """Convert one session folder of ``idx_*`` chunks into the v2 output set:
    one per-track NWB under ``Split_SLPs/``, one ``combined_output.mp4``, and
    one top-level multi-subject NWB linking them, all under *out_dir*.
    """
    input_folder = Path(input_folder)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chunk_folders = discover_chunk_folders(input_folder)
    if not chunk_folders:
        raise ValueError(f"No idx_* chunk folders found in {input_folder}")

    session_start = session_start_time(cfg)

    base_labels = merge_chunk_sleap_labels(chunk_folders)
    track_labels_list = split_labels_by_track(base_labels)
    track_nwbs = write_per_track_nwbs(
        track_labels_list=track_labels_list,
        out_dir=out_dir / SPLIT_SLP_SUBDIRECTORY,
        cfg=cfg,
        session_start=session_start,
        experimenter=cfg["session"]["experimenter"],
        institution=cfg["session"]["institution"],
    )

    combined_video = concat_video_files(chunk_folders=chunk_folders, combined_output=out_dir / COMBINED_VIDEO_NAME)

    out_nwb = out_dir / MULTISUBJECT_NWB_NAME
    build_multisubject_nwb(
        input_folder=input_folder,
        track_nwbs=track_nwbs,
        combined_video=combined_video,
        out_nwb=out_nwb,
        cfg=cfg,
        session_start=session_start,
    )

    return out_dir


def parse_args():
    parser = argparse.ArgumentParser(description="Convert one Sanes session folder of idx_* chunks to NWB")
    parser.add_argument("--input", required=True, type=Path, help="Session folder holding the idx_* chunk folders")
    parser.add_argument("--out", required=True, type=Path, help="Output directory for this session's NWB files")
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
    build_nwb(input_folder=args.input, out_dir=args.out, cfg=cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
