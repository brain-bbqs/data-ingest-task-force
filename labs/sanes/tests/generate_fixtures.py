"""Regenerate the synthetic manifest fixture and its semantic NWB summary.

Run from the repo root with python -m labs.sanes.tests.generate_fixtures.
No real animal metadata or lab media is included.
"""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import numpy
import pynwb

from . import synthetic
from ..code import _sanes_to_nwb as converter

ROOT = Path(__file__).resolve().parent


def summarize(path, /):
    with pynwb.NWBHDF5IO(path, "r") as io:
        nwbfile = io.read()
        audio = nwbfile.acquisition["channel_00"]
        matrix = numpy.column_stack([nwbfile.acquisition[f"channel_{channel:02d}"].data[:] for channel in range(8)])
        summary = {
            "identifier": nwbfile.identifier,
            "session_id": nwbfile.session_id,
            "session_start_time": nwbfile.session_start_time.isoformat(),
            "audio_shape": list(matrix.shape),
            "audio_sha256": hashlib.sha256(matrix.tobytes()).hexdigest(),
            "audio_rate": audio.rate,
            "segments": list(nwbfile.intervals["source_segments"]["segment_id"][:]),
            "subjects_table": nwbfile.subjects_table is not None,
            "videos": {},
        }
        for camera in synthetic.SYNC_CAMERAS:
            series = nwbfile.acquisition[f"video_{camera}"]
            summary["videos"][camera] = {
                "external_file": list(series.external_file[:]),
                "frames": int(series.num_samples),
                "rate": series.rate,
            }
    return summary


def main():
    incoming = ROOT / "example_raw" / "big_arena"
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary)
        session = synthetic.write_sync_session(root=staging / "incoming")
        shutil.copytree(session, incoming / session.name, dirs_exist_ok=True)
        path = converter.build_nwb(
            session_dir=session,
            output_dir=staging / "output",
            config_path=ROOT.parent / "code" / "config_big_arena_2024_12.yaml",
        )
        expected = ROOT / "expected_output" / "big_arena.json"
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.write_text(json.dumps(summarize(path), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
