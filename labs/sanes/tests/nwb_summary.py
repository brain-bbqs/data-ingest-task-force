"""Semantic summary of a manifest session's NWB file, shared by the fixture generator and the integration test.

NWB writes HDF5, which is not byte-stable across library versions, so the golden fixture is this summary of
what the file holds rather than the file itself.
"""

import hashlib

import pynwb


def summarize(path, /):
    with pynwb.NWBHDF5IO(path, "r") as io:
        nwbfile = io.read()
        audio = nwbfile.acquisition["Multi-channel Acoustic Data"]
        matrix = audio.data[:]
        cameras = sorted(name.removeprefix("video_") for name in nwbfile.acquisition if name.startswith("video_"))
        summary = {
            "identifier": nwbfile.identifier,
            "session_id": nwbfile.session_id,
            "session_start_time": nwbfile.session_start_time.isoformat(),
            "audio_neurodata_type": audio.neurodata_type,
            "audio_shape": list(matrix.shape),
            "audio_sha256": hashlib.sha256(matrix.tobytes()).hexdigest(),
            "audio_rate": audio.rate,
            "segments": list(nwbfile.intervals["source_segments"]["segment_id"][:]),
            "subjects_table": nwbfile.subjects_table is not None,
            "videos": {},
        }
        for camera in cameras:
            series = nwbfile.acquisition[f"video_{camera}"]
            summary["videos"][camera] = {
                "external_file": list(series.external_file[:]),
                "frames": int(series.num_samples),
                "rate": series.rate,
            }
    return summary
