"""
_inman_to_nwb.py
================================
Original script developed by Grace Bezold (gbezold1). Some fixes from Neha Thomas (neha-thomas477).

Convert re-structured MATLAB walk session files from the Inman dataset into
Neurodata Without Borders (NWB) 2.x files.

The script is primarily intended for command-line use via ``python _inman_to_nwb.py``.
It parses a single ``.mat`` file that contains synchronized behavioural,
physiological and environmental recordings, assembles them into an
:pyclass:`~pynwb.NWBFile`, applies optional HDF5 compression and writes the
result to disk.

Key responsibilities
--------------------
1. **Configuration parsing** – YAML configuration values control free-text
metadata (e.g. descriptions, units) and recording-device information.
2. **Timestamp handling** – NTP timestamps from the MATLAB file are converted
to UTC ``datetime`` objects and then rescaled to seconds relative to
*t0* (start time) as required by the NWB standard.
3. **NWB construction** – behavioural, eye-tracking, IMU and iEEG modalities
are added to the file using the appropriate NWB table or TimeSeries types.
4. **CLI interface** – exposes a small command-line wrapper for batch
conversion jobs.

All heavy lifting happens inside :pyfunc:`build_nwb`, while the remaining
helpers keep the public surface minimal and testable.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import ntplib
import numpy as np
import yaml
from neuroconv.tools.nwb_helpers import get_default_backend_configuration
from pymatreader import read_mat
from pynwb import NWBHDF5IO, NWBFile
from pynwb.base import DynamicTable
from pynwb.behavior import BehavioralTimeSeries, CompassDirection, EyeTracking, SpatialSeries, TimeSeries
from pynwb.ecephys import LFP, ElectricalSeries
from pynwb.file import Subject

# Data/timing arrays every re-structured walk .mat must carry (see README.md).
REQUIRED_KEYS = [
    "d_amb",
    "ntp_amb",
    "d_gaze_x",
    "d_gaze_y",
    "d_gaze_fix",
    "ntp_gaze",
    "d_kde",
    "ntp_kde",
    "d_imu",
    "ntp_imu",
    "d_np",
    "ntp_np",
    "d_xs",
    "ntp_xs",
]

# Everything the conversion reads from a .mat file. Restricting read_mat to
# these avoids parsing unrelated variables the real files also carry (e.g.
# the original evnts_tbl MATLAB table object, which pymatreader cannot
# reliably import).
READ_KEYS = [*REQUIRED_KEYS, "evnts_struct"]


def load_cfg(cfg_path: Path):
    """
    Load a YAML configuration file.

    Parameters
    ----------
    cfg_path: Absolute or relative :class:`~pathlib.Path` to the YAML file.

    Returns
    -------
    dict: Parsed YAML key/value pairs (empty dict if the file is blank).

    Raises
    ------
    SystemExit: If *cfg_path* does not exist.
    """
    try:
        return yaml.safe_load(cfg_path.read_text()) or {}
    except FileNotFoundError:
        raise SystemExit(f"Config file not found: {cfg_path}")


def cfg_get(*path, CFG, default=None):
    """
    Safely navigate the nested *CFG* dictionary.

    ``cfg_get("section", "sub", CFG=cfg)`` is equivalent to
    ``cfg["section"]["sub"]`` but returns *default* instead of raising a
    ``KeyError`` when any level is missing.

    Parameters
    ----------
    path: Sequence of keys to traverse.
    CFG: Configuration dictionary returned by :pyfunc:`load_cfg`.
    default: Fallback value when the key path does not exist (defaults to ``None``).

    Returns
    -------
    Any: Value found at the requested key path or *default*.
    """
    node = CFG
    for key in path:
        node = node.get(key, {})
    return node or default


def make_rel(data, t0):
    """Compute seconds relative to *t0* for a list/array of datetimes."""
    return [(t - t0).total_seconds() for t in data]


def get_relative_times(data, keys, t0):
    """
    Convert NTP timestamps in *data* to seconds after *t0*.

    Parameters
    ----------
    data: MATLAB structure loaded with :pyfunc:`pymatreader.read_mat` containing ``ntp_<modality>`` arrays.
    keys: Modalities to extract (e.g. ``["amb", "gaze", "imu"]``).
    t0: Start time (UTC aware). Typically the earliest NTP timestamp across all modalities.

    Returns
    -------
    (rel_times, t0): *rel_times* maps each key in *keys* to a list of seconds relative to, *t0* suitable for NWB
    *timestamps*; *t0* is passed through unchanged for convenience.
    """

    all_times = {}

    for key in keys:
        ntp_time = data[f"ntp_{key}"]

        # Handle nested arrays from pymatreader - flatten to 1D array of timestamps
        ntp_array = np.asarray(ntp_time).flatten()

        # Convert NTP timestamps to Unix timestamps (seconds since 1970-01-01)
        # NTP timestamps are seconds since 1900-01-01
        system_ts = [ntplib.ntp_to_system_time(float(ntp_val)) for ntp_val in ntp_array]

        # Convert to timezone-aware datetime objects
        dt_utc = [datetime.fromtimestamp(x, tz=timezone.utc) for x in system_ts]
        all_times[key] = dt_utc

    rel_times = {}
    for key in keys:
        rel_sec = make_rel(all_times[key], t0)
        rel_times[key] = rel_sec

    return rel_times, t0


def check_time_zero_axis(data, name):
    """Warn when *data* appears to have the time dimension in the wrong axis."""
    if len(data.shape) > 1:
        if data.shape[1] > data.shape[0]:  # heuristic that there will normally have more rows of time than cols
            print(f"Check that {name} has time as 0th axis")

    return


def build_nwb(data, subject_name, session, out_nwb, cfg):
    """
    Assemble an :pyclass:`pynwb.NWBFile` from MATLAB *data* and write *out_nwb*.

    The function is intentionally large but linear: parse metadata → convert
    timestamps → create NWB containers → write to disk.

    Parameters
    ----------
    data: Output of :pyfunc:`pymatreader.read_mat` containing both data (``d_*``) and timing (``ntp_*``) arrays.
    subject_name: String identifier for the human participant (e.g. ``"03"``).
    session: Walk session number starting from 1.
    out_nwb: Path to the target ``.nwb`` file (will be overwritten).
    cfg: Parsed YAML configuration with recording‑specific metadata.

    Returns
    -------
    None
    *The NWB file is written as a side effect. A short confirmation message is printed*
    """

    date_string = cfg_get("session", "start_time", CFG=cfg)
    date_format = "%Y-%m-%d%H:%M:%S%z"
    session_start = datetime.strptime(date_string, date_format)

    # create NWB file
    nwbfile = NWBFile(
        session_description=cfg_get(
            "session", "description", CFG=cfg
        ),  # hardcode what session is/information in this block
        identifier=f"InmanWalk-Subject{subject_name}-Walk{session}",
        session_start_time=session_start,
        experimenter=cfg_get("session", "experimenter", CFG=cfg),
        institution=cfg_get("session", "institution", CFG=cfg),
    )

    # subject definition
    subject_id = subject_name
    species = cfg_get("subject", "species", CFG=cfg)
    age = cfg_get("subject", "age", CFG=cfg)
    sex = cfg_get("subject", "sex", CFG=cfg)
    description_subject = cfg_get("subject", "description", CFG=cfg)

    nwb_subject = Subject(
        subject_id=subject_id,
        species=species,
        description=description_subject,
        age=age,
        sex=sex,
    )

    nwbfile.subject = nwb_subject

    t0 = cfg_get("session", "start_time", CFG=cfg)  # assumes start_time is in datetime utc
    t0_datetime = datetime.strptime(t0, date_format)

    # Ensure t0 is timezone-aware (should match the timezone in the config string)
    # If no timezone in t0_datetime, it means the format parsing captured it
    if t0_datetime.tzinfo is None:
        # This shouldn't happen if date_format includes %z, but handle it gracefully
        t0_datetime = t0_datetime.replace(tzinfo=timezone.utc)

    # make NTP timestamps NWB compatible by making them seconds relative to start
    keys = ["amb", "gaze", "kde", "imu", "np", "xs"]
    rel_times, _ = get_relative_times(data, keys, t0_datetime)

    # Processing: behavior/kinematics container
    beh = nwbfile.create_processing_module(name="behavior", description="Kinematic and derived data")

    # ambient light packaging
    ambient_light_series = TimeSeries(
        name="AmbientLight",
        description=cfg_get("timeseries", "ambient_light", "description", CFG=cfg),
        data=data["d_amb"],
        timestamps=rel_times["amb"],  # TODO: verify rel_times arr matches data arr
        unit=cfg_get("timeseries", "ambient_light", "unit", CFG=cfg),
    )

    nwbfile.add_acquisition(ambient_light_series)

    # add kde to behavioral
    kde_series = TimeSeries(
        name="KernelDensityEstimation",
        description=cfg_get("timeseries", "kde", "description", CFG=cfg),
        data=data["d_kde"],
        timestamps=rel_times["kde"],
        unit=cfg_get("timeseries", "kde", "unit", CFG=cfg),
    )

    significant_beh = BehavioralTimeSeries(name="KDE-SignificantBehCalc", time_series=kde_series)

    beh.add(significant_beh)

    # add movement velocity
    velocity_time_series = TimeSeries(
        name="MovementVelocity",
        description=cfg_get("timeseries", "movement_velocity", "description", CFG=cfg),
        data=data["d_xs"],
        timestamps=rel_times["xs"],
        unit=cfg_get("timeseries", "movement_velocity", "unit", CFG=cfg),
    )

    movement_velocity = BehavioralTimeSeries(name="MovementVelocityBehavioral", time_series=velocity_time_series)

    beh.add(movement_velocity)

    # eye tracker data packaging

    # add eye tracker device to NWB file
    nwbfile.create_device(
        name=cfg_get("device_eyetracker", "name", CFG=cfg),
        description=cfg_get("device_eyetracker", "description", CFG=cfg),
    )

    gaze_x = np.asarray(data["d_gaze_x"])
    gaze_y = np.asarray(data["d_gaze_y"])
    gaze_data = np.column_stack((gaze_x, gaze_y))

    gaze_spatial_series = SpatialSeries(
        name="GazePosition",
        description=cfg_get("timeseries", "gaze_position", "description", CFG=cfg),
        data=gaze_data,
        timestamps=rel_times["gaze"],
        reference_frame=cfg_get("timeseries", "gaze_position", "reference_frame", CFG=cfg),
        unit=cfg_get("timeseries", "gaze_position", "unit", CFG=cfg),
    )

    eye_tracking = EyeTracking(
        name="EyeTracking",
        spatial_series=gaze_spatial_series,
    )

    fixation_time_series = TimeSeries(
        name="GazeFixation",
        description=cfg_get("timeseries", "gaze_fixation", "description", CFG=cfg),
        data=data["d_gaze_fix"],
        timestamps=rel_times["gaze"],
        unit=cfg_get("timeseries", "gaze_fixation", "unit", CFG=cfg),
    )

    fixation_behavioral_ts = BehavioralTimeSeries(
        name="GazeFixationBehavioral",
        time_series=fixation_time_series,
    )

    beh.add(eye_tracking)
    beh.add(fixation_behavioral_ts)

    # package IMU data
    nwbfile.create_device(
        name=cfg_get("device_imu", "name", CFG=cfg),
        description=cfg_get("device_imu", "description", CFG=cfg),
    )

    # Gyro and acceleration are not spatial positions, so they are plain
    # TimeSeries -- SpatialSeries only permits spatial units (DANDI rejects
    # 'deg/s' or 'm/s²' there).
    gyro_x = np.asarray(data["d_imu"]["gyroX"])
    gyro_y = np.asarray(data["d_imu"]["gyroY"])
    gyro_z = np.asarray(data["d_imu"]["gyroZ"])
    gyro_data = np.column_stack((gyro_x, gyro_y, gyro_z))

    imu_gyro_series = TimeSeries(
        name="IMUGyro",
        description=cfg_get("timeseries", "imu_gyro", "description", CFG=cfg),
        data=gyro_data,
        timestamps=rel_times["imu"],
        unit=cfg_get("timeseries", "imu_gyro", "unit", CFG=cfg),
    )

    accel_x = np.asarray(data["d_imu"]["accelX"])
    accel_y = np.asarray(data["d_imu"]["accelY"])
    accel_z = np.asarray(data["d_imu"]["accelZ"])
    accel_data = np.column_stack((accel_x, accel_y, accel_z))

    imu_accel_series = TimeSeries(
        name="IMUAccel",
        description=cfg_get("timeseries", "imu_accel", "description", CFG=cfg),
        data=accel_data,
        timestamps=rel_times["imu"],
        unit=cfg_get("timeseries", "imu_accel", "unit", CFG=cfg),
    )

    roll = np.asarray(data["d_imu"]["roll"])
    pitch = np.asarray(data["d_imu"]["pitch"])
    orientation_data = np.column_stack((roll, pitch))

    imu_orientation_spatial_series = SpatialSeries(
        name="IMUOrientation",
        description=cfg_get("timeseries", "imu_orientation", "description", CFG=cfg),
        data=orientation_data,
        timestamps=rel_times["imu"],
        reference_frame=cfg_get("timeseries", "imu_orientation", "reference_frame", CFG=cfg),
        unit=cfg_get("timeseries", "imu_orientation", "unit", CFG=cfg),
    )

    imu_compass_direction = CompassDirection(
        spatial_series=imu_orientation_spatial_series,
        name="IMUCompassDirection",
    )

    beh.add(imu_gyro_series)
    beh.add(imu_accel_series)
    beh.add(imu_compass_direction)

    behavior_annotation_data = data["evnts_struct"]
    n = len(behavior_annotation_data["Description"])

    description_data = np.array([str(behavior_annotation_data["Description"][i]) for i in range(n)], dtype=str)
    event_data = np.array([str(behavior_annotation_data["Event"][i]) for i in range(n)], dtype=str)
    pupil_frame_data = np.array([int(behavior_annotation_data["PupilFrame"][i]) for i in range(n)], dtype=np.int64)
    gopro_frame_data = np.array([int(behavior_annotation_data["GoProFrame"][i]) for i in range(n)], dtype=np.int64)
    np_sample_data = np.array([int(behavior_annotation_data["NPSample"][i]) for i in range(n)], dtype=np.int64)
    ntp_data = np.array([float(behavior_annotation_data["NTP"][i]) for i in range(n)], dtype=np.float64)
    ntp_relative_data = np.array(
        [
            (datetime.fromtimestamp(ntplib.ntp_to_system_time(ntp), tz=timezone.utc) - t0_datetime).total_seconds()
            for ntp in ntp_data
        ],
        dtype=np.float64,
    )

    n = len(description_data)
    assert all(
        len(x) == n
        for x in [event_data, pupil_frame_data, gopro_frame_data, np_sample_data, ntp_data, ntp_relative_data]
    )

    # add behavior/annotations table
    annotation_table = DynamicTable(
        name="BehaviorAnnotations", description="Annotations of behavioral events", id=list(range(n))
    )

    annotation_table.add_column(
        name="Annotation", description="Annotations and labels of the event", data=description_data
    )
    annotation_table.add_column(name="Event", description="Event code/label", data=event_data)
    annotation_table.add_column(name="PupilFrame", description="Pupil frame index", data=pupil_frame_data)
    annotation_table.add_column(name="GoProFrame", description="GoPro frame index", data=gopro_frame_data)
    annotation_table.add_column(name="NPSample", description="Neural probe sample index", data=np_sample_data)
    annotation_table.add_column(name="NTP", description="Absolute NTP time (s)", data=ntp_data)
    annotation_table.add_column(name="NTPRelative", description="Time relative to t0 (s)", data=ntp_relative_data)

    beh.add(annotation_table)

    # add iEEG data
    device_iEEG = nwbfile.create_device(
        name=cfg_get("device_ieeg", "name", CFG=cfg),
        description=cfg_get("device_ieeg", "description", CFG=cfg),
    )

    electrode_group1 = nwbfile.create_electrode_group(
        name=cfg_get("electrode_group1", "name", CFG=cfg),
        description=cfg_get("electrode_group1", "description", CFG=cfg),
        device=device_iEEG,
        location=cfg_get("electrode_group1", "location", CFG=cfg),
    )

    channelmap = cfg_get("channelmap", CFG=cfg)

    nwbfile.add_electrode_column(name="label", description="label of electrode")
    for channel_name, channel_data in channelmap.items():
        nwbfile.add_electrode(
            x=channel_data["x"],
            y=channel_data["y"],
            z=channel_data["z"],
            group=electrode_group1,
            label=channel_name,
            location="MTL",
            filtering=channel_data["filtering"],
        )

    all_table_region = nwbfile.create_electrode_table_region(
        region=list(range(len(channelmap))),  # reference row indices 0 to N-1
        description="all electrodes",
    )

    lfp_electrical_series = ElectricalSeries(
        name="ElectricalSeries",
        description=cfg_get("lfp", "description", CFG=cfg),
        data=data["d_np"],
        filtering=cfg_get("lfp", "filtering", CFG=cfg),
        electrodes=all_table_region,
        timestamps=rel_times["np"],
    )

    lfp = LFP(electrical_series=lfp_electrical_series)

    ecephys_module = nwbfile.create_processing_module(
        name="iEEG", description="Processed intracranial electroencephalography data."
    )

    ecephys_module.add(lfp)

    # compress NWB file
    backend_configuration = get_default_backend_configuration(nwbfile, backend="hdf5")
    backend_configuration.apply_global_compression(
        compression_method="gzip", compression_options={"compression_opts": 4}
    )

    with NWBHDF5IO(out_nwb, "w") as io:
        io.write(nwbfile)

    print(f"Wrote NWB file to: {out_nwb}")
    return


def parse_args() -> argparse.Namespace:

    p = argparse.ArgumentParser(description="Convert MATLAB .mat to NWB")
    p.add_argument("--mat", required=True, type=Path, help="Path to input .mat file")
    p.add_argument("--subject", required=True, help="Subject identifier (string)")
    p.add_argument("--session", required=True, type=int, help="Session number (int)")
    p.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="YAML config (default: ./config.yaml)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output NWB file path (default: derive from --mat)",
    )
    return p.parse_args()


def main():

    print("parsing args")

    args = parse_args()

    cfg = load_cfg(args.config)
    mat_data = read_mat(args.mat, variable_names=READ_KEYS)

    missing = [k for k in REQUIRED_KEYS if k not in mat_data]
    if missing:
        raise SystemExit(f"Missing keys in MAT data: {missing}")
    else:
        print("All keys found")

    out_path = args.out
    if out_path is None:
        out_path = args.mat.with_suffix("")
        out_path = out_path.parent / f"{out_path.name}_S{args.subject}_W{args.session}.nwb"
    else:
        print(f"out path: {out_path}")

    build_nwb(data=mat_data, subject_name=args.subject, session=args.session, out_nwb=out_path, cfg=cfg)


if __name__ == "__main__":

    """
    Example CLI usage
    --------
    python _inman_to_nwb.py --mat example_data/RWNApp_RW3_Walk1_restructured.mat --subject 3 --session 1 \
        --config ./config.yaml --out ./InmanWalk-S03-Walk1.nwb
    """
    print("calling main")

    main()
