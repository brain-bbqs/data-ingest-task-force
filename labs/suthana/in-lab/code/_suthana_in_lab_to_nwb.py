#!/usr/bin/env python3
"""
_suthana_in_lab_to_nwb.py
=========================
Original script developed by Neha Thomas (Suthana_inLab_DataConversion.py /
Suthana_MATdata_full.ipynb). Ported here and adapted for the ingest pipeline.

Convert one subject's aligned in-lab navigation recording (a MATLAB v7.3
``.mat`` file holding a ``Trajectories`` struct) into a single NWB file.

One ``.mat`` file is one subject's whole experiment, split into several
non-contiguous recording segments. Every segment contributes its own series
to the same NWB file, positioned by a ``starting_time`` measured from the
session start. Segment start times come from a companion
``Trajectories_runtimes.csv``, one column per subject and one row per
segment.

Key responsibilities
--------------------
1. **Configuration parsing** - YAML configuration supplies every value the
   original script hardcoded: session and device metadata, the subject
   table, the scalp EEG montage, and the de-identification settings.
2. **Timestamp handling** - segment start times are read as local wall-clock
   times, shifted by a per-subject de-identification offset, and expressed
   as seconds relative to the session start, as NWB requires.
3. **NWB construction** - behaviour (head rotation, gaze, body-part
   centroids), iEEG, scalp EEG, and the beep/button event tables are added
   to the file with the appropriate NWB types.
4. **CLI interface** - a small command-line wrapper for converting one
   subject. ``batch_convert.py`` drives it over a whole incoming dandiset.

All of the assembly happens inside :pyfunc:`build_nwb`, which takes an open
:pyclass:`h5py.File` so the caller controls the file's lifetime.

Deviations from the original script are listed in ``../README.md``. The
substantive ones are that the de-identification offset is derived
deterministically instead of drawn from an unseeded RNG, and that the scalp
EEG artifact mask now stores the scalp EEG mask rather than a copy of the
iEEG one.
"""

from __future__ import annotations

import argparse
import hashlib
import random
from datetime import timedelta
from pathlib import Path

import h5py
import numpy
import pandas
import yaml
from neuroconv.tools import configure_and_write_nwbfile
from neuroconv.tools.nwb_helpers import get_default_backend_configuration
from pynwb import NWBFile, TimeSeries
from pynwb.behavior import CompassDirection, EyeTracking, Position, SpatialSeries
from pynwb.ecephys import ElectricalSeries
from pynwb.file import DynamicTable, Subject

RUNTIMES_FILENAME = "Trajectories_runtimes.csv"

IEEG_CHANNEL_COUNT = 4

# Rows of the position matrix belonging to each tracked body part, and the
# NWB container each set of centroids goes into. The original script sliced
# these positions out by hand; the layout is the same.
POSITION_PARTS = (
    ("Hip", slice(0, 2)),
    ("LeftLeg", slice(2, 5)),
    ("RightLeg", slice(5, 8)),
    ("Head", slice(8, 10)),
)


def load_cfg(cfg_path, /):
    """Load a YAML configuration file into a dict."""
    cfg = yaml.safe_load(Path(cfg_path).read_text())
    return cfg


def decode_matlab_string(values, /):
    """Decode a MATLAB char array stored as uint16 code points.

    MATLAB v7.3 writes char arrays as arrays of UTF-16 code units. Both
    string shapes the raw files use (label arrays and event-table entries)
    read back this way.
    """
    text = "".join(chr(code) for code in numpy.asarray(values).flatten())
    return text.strip()


def dereference_strings(mat_file, refs, /):
    """Decode every MATLAB string behind a 1-D array of HDF5 object references."""
    strings = [decode_matlab_string(mat_file[ref][()]) for ref in numpy.asarray(refs).flatten()]
    return strings


def dereference_scalars(mat_file, refs, /):
    """Read every scalar behind a 1-D array of HDF5 object references as int."""
    scalars = numpy.array(
        [int(numpy.asarray(mat_file[ref][()]).item()) for ref in numpy.asarray(refs).flatten()],
        dtype=int,
    )
    return scalars


def column_labels(mat_file, entry, /):
    """The per-column labels of a recording entry, from its ``hdr`` table.

    ``hdr`` is an (ncolumns, 2) array of object references whose second
    column holds the label strings.
    """
    labels = dereference_strings(mat_file, entry["hdr"][()][:, 1])
    return labels


def deidentification_offset(*, subject_id, cfg):
    """The timedelta every timestamp of *subject_id* is shifted by.

    The original script drew this from an unseeded ``random``, so a re-run
    produced different session start times for the same input. Dispatch
    re-runs the conversion whenever the script changes, which would have
    rewritten every session's start time each time. Seeding a private
    ``random.Random`` with the configured seed and the subject id keeps the
    shift stable across runs while preserving the original's distribution.
    """
    settings = cfg.get("deidentification", {})
    if not settings.get("enabled", False):
        return timedelta(0)
    seed_material = f"{settings.get('seed', '')}/{subject_id}".encode()
    generator = random.Random(hashlib.sha256(seed_material).hexdigest())
    max_days = int(settings.get("max_day_offset", 365))
    max_seconds = int(settings.get("max_second_offset", 43200))
    offset = timedelta(
        days=generator.randint(-max_days, max_days),
        seconds=generator.randint(-max_seconds, max_seconds),
    )
    return offset


def read_subject_id(mat_file, /):
    """The raw subject id (e.g. ``R056``) stored in the ``Trajectories`` struct."""
    subject_id = decode_matlab_string(mat_file["Trajectories"]["Subject_ID"][()])
    return subject_id


def segment_start_times(*, runtimes_path, paper_id, cfg):
    """Localized, de-identification-shifted start time of every segment.

    ``Trajectories_runtimes.csv`` carries one column per subject, named so
    that the subject's paper id appears in the column header, and one row
    per recording segment.
    """
    runtimes = pandas.read_csv(runtimes_path)
    matching = [column for column in runtimes.columns if paper_id in column]
    if not matching:
        raise ValueError(f"{runtimes_path} has no column for subject {paper_id!r}")
    timezone = cfg.get("timezone", "America/Los_Angeles")
    times = pandas.to_datetime(runtimes[matching[0]]).dt.tz_localize(timezone)
    offset = deidentification_offset(subject_id=paper_id, cfg=cfg)
    shifted = [time + offset for time in times]
    return shifted


def add_electrodes(*, nwbfile, cfg, ieeg_channels):
    """Build both electrode tables and return their table regions.

    The iEEG channels come first so their row indices match the channel
    order of the recorded iEEG data, then the scalp EEG montage.
    """
    nwbfile.add_electrode_column(name="label", description="label of electrode")

    ieeg_device = nwbfile.create_device(**cfg["device_ieeg"])
    ieeg_group = nwbfile.create_electrode_group(device=ieeg_device, **cfg["electrode_group_ieeg"])
    for index in range(IEEG_CHANNEL_COUNT):
        nwbfile.add_electrode(group=ieeg_group, label=f"iEEG {index}", location=ieeg_channels[index])
    ieeg_region = nwbfile.create_electrode_table_region(
        region=list(range(IEEG_CHANNEL_COUNT)),
        description="iEEG electrodes",
    )

    scalp_channels = cfg["scalp_eeg_channels"]
    scalp_device = nwbfile.create_device(**cfg["device_scalp_eeg"])
    scalp_group = nwbfile.create_electrode_group(device=scalp_device, **cfg["electrode_group_scalp_eeg"])
    for index, channel in enumerate(scalp_channels):
        nwbfile.add_electrode(group=scalp_group, label=f"sEEG {index}: {channel}", location=channel)
    scalp_region = nwbfile.create_electrode_table_region(
        region=list(range(IEEG_CHANNEL_COUNT, IEEG_CHANNEL_COUNT + len(scalp_channels))),
        description="sEEG electrodes",
    )

    return ieeg_region, scalp_region


def add_head_rotation(*, mat_file, entry, containers, segment, start_time, rate, cfg):
    labels = column_labels(mat_file, entry)
    series = SpatialSeries(
        name=f"Head Rotation Segment {segment:02d}",
        description=f"Head rotation data with 3 columns: {', '.join(labels)}",
        data=entry["data"][()].T,
        starting_time=start_time,
        rate=rate,
        reference_frame=cfg["behavior"]["head_rotation"]["reference_frame"],
        unit=cfg["behavior"]["head_rotation"]["unit"],
    )
    containers["head_rotation"].add_spatial_series(series)


def add_gaze(*, gaze_data, containers, segment, start_time, rate, cfg):
    gaze_cfg = cfg["behavior"]["gaze"]
    series = SpatialSeries(
        name=f"Gaze Position Segment {segment:02d}",
        description=gaze_cfg["description"],
        data=gaze_data.T,
        starting_time=start_time,
        rate=rate,
        reference_frame=gaze_cfg["reference_frame"],
        unit=gaze_cfg["unit"],
    )
    containers["gaze"].add_spatial_series(series)


def add_position(*, mat_file, entry, containers, segment, start_time, rate, cfg):
    position_cfg = cfg["behavior"]["position"]
    positions = entry["data"][()]
    labels = column_labels(mat_file, entry)
    for part, rows in POSITION_PARTS:
        part_labels = labels[rows]
        series = SpatialSeries(
            name=f"{part} Centroid Segment {segment:02d}",
            description=f"Centroid of {part} with labels {', '.join(part_labels)}",
            data=positions[rows, :].T,
            starting_time=start_time,
            rate=rate,
            reference_frame=position_cfg["reference_frame"],
            unit=position_cfg["unit"],
        )
        containers[part].add_spatial_series(series)


def add_electrical_series(*, module, entry, electrodes, segment, start_time, rate, label, mask_key, conversion):
    """One segment's electrical series plus its artifact mask.

    The mask is a boolean array over the same samples; it is stored as
    uint8 because NWB has no boolean TimeSeries dtype.
    """
    series = ElectricalSeries(
        name=f"Processed {label} Segment {segment:02d}",
        description=f"Processed {label} data Segment {segment:02d}",
        data=entry["data"][()].T,
        electrodes=electrodes,
        starting_time=start_time,
        rate=rate,
        conversion=conversion,
    )
    mask = TimeSeries(
        name=f"{label} Artifact Series Segment {segment:02d}",
        description=(
            f"Boolean series indicating the presence of artifacts (1 = artifact) in the {label} data. "
            f"Use this series as a mask to exclude artifacts present in Processed {label} Segment "
            f"{segment:02d}."
        ),
        data=entry[mask_key][()].T.astype("uint8"),
        starting_time=start_time,
        rate=rate,
        unit="na",
    )
    module.add(series)
    module.add(mask)
    return series


def read_events(*, mat_file, entry, segment, sample_times):
    """The beep and button event rows recorded during one segment.

    Event rows carry a 1-based sample index into the segment's recording;
    ``sample_times`` converts that to a session-relative time in seconds.
    """
    beep = entry["beep"][()]
    button = entry["button"][()]

    beep_indices = dereference_scalars(mat_file, beep[0, :])
    beep_rows = pandas.DataFrame(
        {
            "Segment": numpy.full(beep_indices.size, segment, dtype=int),
            "Index": beep_indices,
            "Time": sample_times[beep_indices - 1],
            "Object": dereference_strings(mat_file, beep[1, :]),
        }
    )

    button_indices = dereference_scalars(mat_file, button[0, :])
    button_rows = pandas.DataFrame(
        {
            "Segment": numpy.full(button_indices.size, segment, dtype=int),
            "Index": button_indices,
            "Time": sample_times[button_indices - 1],
            "Response": dereference_strings(mat_file, button[1, :]),
            "Score": dereference_scalars(mat_file, button[2, :]),
            "Attempts": dereference_scalars(mat_file, button[3, :]),
            "Correct": dereference_scalars(mat_file, button[4, :]),
        }
    )

    return beep_rows, button_rows


BEEP_COLUMNS = [
    dict(name="Segment", description="Segment number corresponding to the data segment in the NWB file"),
    dict(name="Index", description="Index of timestamp when beep occurred"),
    dict(name="Time", description="Time (in seconds) of the beep event, relative to the session start"),
    dict(name="Object", description="Object closest to participant"),
]

BUTTON_COLUMNS = [
    dict(name="Segment", description="Segment number corresponding to the data segment in the NWB file"),
    dict(name="Index", description="Index of timestamp when participant responded"),
    dict(name="Time", description="Time (in seconds) of the response event, relative to the session start"),
    dict(
        name="Response",
        description="Left button = first object, middle button = second object, right button = third object",
    ),
    dict(name="Score", description="Number of total correct"),
    dict(name="Attempts", description="Number of times participant was asked to respond"),
    dict(name="Correct", description="1 = correct answer, -1 = incorrect answer, 0 = no response"),
]


def build_nwb(*, mat_file, subject_id, start_times, out_nwb, cfg):
    """Assemble and write one subject's NWB file.

    Parameters
    ----------
    mat_file : h5py.File
        The subject's aligned ``.mat`` file, open for reading.
    subject_id : str
        The raw subject id (e.g. ``R056``), used to look up the subject
        entry in the config.
    start_times : list of pandas.Timestamp
        One localized start time per recording segment, already shifted for
        de-identification.
    out_nwb : Path
        Destination path. Its parent is created if needed.
    cfg : dict
        Parsed configuration (see ``config.yaml``).
    """
    subject_cfg = cfg["subjects"][subject_id]
    paper_id = subject_cfg["paper_id"]

    trajectories = mat_file["Trajectories"]
    rate = float(numpy.asarray(trajectories["Fs"][()]).item())
    recordings = trajectories["recordings"]
    segment_count = len(recordings["scalp_EEG"])
    if len(start_times) < segment_count:
        raise ValueError(
            f"{RUNTIMES_FILENAME} lists {len(start_times)} segment start time(s) for subject "
            f"{paper_id}, but the .mat file holds {segment_count}"
        )
    session_start_time = start_times[0]

    session_cfg = cfg["session"]
    nwbfile = NWBFile(
        session_description=session_cfg["description"],
        identifier=f"SuthanaInLab-{paper_id}",
        session_start_time=session_start_time,
        experimenter=list(session_cfg["experimenter"]),
        lab=session_cfg["lab"],
        institution=session_cfg["institution"],
        experiment_description=session_cfg["experiment_description"],
        keywords=list(session_cfg["keywords"]),
        related_publications=list(session_cfg.get("related_publications", [])),
    )
    nwbfile.subject = Subject(
        subject_id=paper_id,
        species=cfg["subject"]["species"],
        age=subject_cfg["age"],
        sex=subject_cfg["sex"],
        description=f"Subject {paper_id}",
    )

    ieeg_module = nwbfile.create_processing_module(name="iEEG", description="Processed iEEG data")
    scalp_module = nwbfile.create_processing_module(name="scalp EEG", description="Processed scalp EEG data")
    behavior_module = nwbfile.create_processing_module(name="behavior", description="Processed behavioral data")

    ieeg_region, scalp_region = add_electrodes(nwbfile=nwbfile, cfg=cfg, ieeg_channels=subject_cfg["ieeg_channels"])

    containers = {
        "head_rotation": CompassDirection(name="HeadRotation_All"),
        "gaze": EyeTracking(name="EyeTracking_All"),
        **{part: Position(name=f"Pose_{part}_All") for part, _ in POSITION_PARTS},
    }

    beep_frames = []
    button_frames = []
    for index in range(segment_count):
        segment = index + 1
        start_time = (start_times[index] - session_start_time).total_seconds()

        add_head_rotation(
            mat_file=mat_file,
            entry=mat_file[recordings["head_rotation"][index][0]],
            containers=containers,
            segment=segment,
            start_time=start_time,
            rate=rate,
            cfg=cfg,
        )
        add_gaze(
            gaze_data=mat_file[recordings["gaze"][index][0]][()],
            containers=containers,
            segment=segment,
            start_time=start_time,
            rate=rate,
            cfg=cfg,
        )
        add_position(
            mat_file=mat_file,
            entry=mat_file[recordings["position"][index][0]],
            containers=containers,
            segment=segment,
            start_time=start_time,
            rate=rate,
            cfg=cfg,
        )
        add_electrical_series(
            module=ieeg_module,
            entry=mat_file[recordings["iEEG"][index][0]],
            electrodes=ieeg_region,
            segment=segment,
            start_time=start_time,
            rate=rate,
            label="iEEG",
            mask_key="ix_IED",
            conversion=float(cfg["ecephys"]["ieeg"]["conversion"]),
        )
        scalp_series = add_electrical_series(
            module=scalp_module,
            entry=mat_file[recordings["scalp_EEG"][index][0]],
            electrodes=scalp_region,
            segment=segment,
            start_time=start_time,
            rate=rate,
            label="scalp EEG",
            mask_key="ix_art",
            conversion=float(cfg["ecephys"]["scalp_eeg"]["conversion"]),
        )

        sample_times = scalp_series.starting_time + numpy.arange(scalp_series.data.shape[0]) / scalp_series.rate
        beep_rows, button_rows = read_events(
            mat_file=mat_file,
            entry=mat_file[recordings["events"][index][0]],
            segment=segment,
            sample_times=sample_times,
        )
        beep_frames.append(beep_rows)
        button_frames.append(button_rows)

    for container in containers.values():
        behavior_module.add(container)

    beep_events = pandas.concat(beep_frames, ignore_index=True).sort_values("Time").reset_index(drop=True)
    button_events = pandas.concat(button_frames, ignore_index=True).sort_values("Time").reset_index(drop=True)
    behavior_module.add(
        DynamicTable.from_dataframe(
            beep_events,
            name="beep_events",
            table_description=cfg["behavior"]["beep_events"]["description"],
            columns=BEEP_COLUMNS,
        )
    )
    behavior_module.add(
        DynamicTable.from_dataframe(
            button_events,
            name="button_events",
            table_description=cfg["behavior"]["button_events"]["description"],
            columns=BUTTON_COLUMNS,
        )
    )

    out_nwb = Path(out_nwb)
    out_nwb.parent.mkdir(parents=True, exist_ok=True)
    backend_configuration = get_default_backend_configuration(nwbfile, backend="hdf5")
    backend_configuration.apply_global_compression(
        compression_method=cfg["compression"]["method"],
        compression_options={"compression_opts": int(cfg["compression"]["level"])},
    )
    configure_and_write_nwbfile(nwbfile, nwbfile_path=out_nwb, backend_configuration=backend_configuration)


def convert_subject(*, mat_path, runtimes_path, out_nwb, cfg):
    """Convert one aligned ``.mat`` file into one NWB file."""
    with h5py.File(mat_path, "r") as mat_file:
        subject_id = read_subject_id(mat_file)
        if subject_id not in cfg["subjects"]:
            raise ValueError(f"{mat_path} names subject {subject_id!r}, which config.yaml does not describe")
        paper_id = cfg["subjects"][subject_id]["paper_id"]
        start_times = segment_start_times(runtimes_path=runtimes_path, paper_id=paper_id, cfg=cfg)
        build_nwb(
            mat_file=mat_file,
            subject_id=subject_id,
            start_times=start_times,
            out_nwb=out_nwb,
            cfg=cfg,
        )


def parse_args():
    parser = argparse.ArgumentParser(description="Convert one Suthana in-lab .mat recording to NWB")
    parser.add_argument("--mat", required=True, type=Path, help="Aligned .mat file for one subject")
    parser.add_argument(
        "--runtimes",
        type=Path,
        default=None,
        help=f"Segment start times CSV (default: {RUNTIMES_FILENAME} beside --mat)",
    )
    parser.add_argument("--out", required=True, type=Path, help="Destination NWB file")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.yaml",
        help="YAML config (default: config.yaml next to this script)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    runtimes_path = args.runtimes if args.runtimes is not None else args.mat.parent / RUNTIMES_FILENAME
    convert_subject(
        mat_path=args.mat,
        runtimes_path=runtimes_path,
        out_nwb=args.out,
        cfg=load_cfg(args.config),
    )
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
