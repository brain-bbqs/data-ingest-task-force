#!/usr/bin/env python3
"""Generate the committed mock input fixture for the integration test.

Writes ``tests/example_raw/RWNApp_RW3_Walk1_restructured.mat``, a tiny but
structurally faithful stand-in for one re-structured Inman walk session (see
``code/README.md`` for the real data layout). All values are deterministic so
regenerating the fixture is reproducible.

Run with::

    python3 tests/generate_fixtures.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy
import scipy.io

TESTS = Path(__file__).resolve().parent
EXAMPLE_RAW = TESTS / "example_raw"

# Must stay in sync with session.start_time in tests/config.yaml.
SESSION_START = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

# Offset between the NTP epoch (1900) and the Unix epoch (1970), in seconds.
NTP_DELTA = 2208988800.0

SAMPLE_COUNT = 20


def _ntp_timestamps(second_offsets, /):
    unix_times = SESSION_START.timestamp() + numpy.asarray(second_offsets, dtype=numpy.float64)
    ntp_times = unix_times + NTP_DELTA
    return ntp_times


def build_session_dict():
    offsets = numpy.arange(SAMPLE_COUNT) * 0.1
    ntp = _ntp_timestamps(offsets)

    session = {
        "d_amb": numpy.linspace(100.0, 119.0, SAMPLE_COUNT),
        "ntp_amb": ntp,
        "d_gaze_x": numpy.linspace(0.0, 19.0, SAMPLE_COUNT),
        "d_gaze_y": numpy.linspace(20.0, 39.0, SAMPLE_COUNT),
        "d_gaze_fix": numpy.tile([0.0, 1.0], SAMPLE_COUNT // 2),
        "ntp_gaze": ntp,
        "d_kde": numpy.linspace(0.0, 1.0, SAMPLE_COUNT),
        "ntp_kde": ntp,
        "d_imu": {
            "gyroX": numpy.linspace(-1.0, 1.0, SAMPLE_COUNT),
            "gyroY": numpy.linspace(-2.0, 2.0, SAMPLE_COUNT),
            "gyroZ": numpy.linspace(-3.0, 3.0, SAMPLE_COUNT),
            "accelX": numpy.linspace(0.0, 0.5, SAMPLE_COUNT),
            "accelY": numpy.linspace(0.5, 1.0, SAMPLE_COUNT),
            "accelZ": numpy.linspace(9.5, 10.0, SAMPLE_COUNT),
            "roll": numpy.linspace(-10.0, 10.0, SAMPLE_COUNT),
            "pitch": numpy.linspace(-5.0, 5.0, SAMPLE_COUNT),
        },
        "ntp_imu": ntp,
        "d_np": numpy.arange(SAMPLE_COUNT * 4, dtype=numpy.float64).reshape(SAMPLE_COUNT, 4) * 1e-3,
        "ntp_np": ntp,
        "d_xs": numpy.linspace(50.0, 69.0, SAMPLE_COUNT),
        "ntp_xs": ntp,
        # The real files carry evnts_tbl converted to a struct (table2struct);
        # scipy.io round-trips this dict-of-arrays shape the same way
        # pymatreader reads the real struct: one array per column.
        "evnts_struct": {
            "Description": numpy.array(["Walk start", "Turn left", "Walk end"], dtype=object),
            "Event": numpy.array(["start", "turn", "end"], dtype=object),
            "PupilFrame": numpy.array([1.0, 50.0, 100.0]),
            "GoProFrame": numpy.array([2.0, 60.0, 120.0]),
            "NPSample": numpy.array([10.0, 500.0, 1000.0]),
            "NTP": _ntp_timestamps([0.0, 1.0, 1.9]),
        },
    }
    return session


def main():
    EXAMPLE_RAW.mkdir(parents=True, exist_ok=True)
    out_path = EXAMPLE_RAW / "RWNApp_RW3_Walk1_restructured.mat"
    scipy.io.savemat(out_path, build_session_dict())
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
