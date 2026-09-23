"""Structural summary of a converted session, shared by the fixture generator and the integration test.

NWB writes HDF5, which is not byte-stable across library versions, so the
golden fixture is this JSON-able summary of what the files contain rather
than the files themselves.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy
import pynwb


def _sha256(array, /):
    digest = hashlib.sha256(numpy.ascontiguousarray(array).tobytes()).hexdigest()
    return digest


def summarize_nwb(path, /):
    with pynwb.NWBHDF5IO(path, "r") as io:
        nwbfile = io.read()
        series = nwbfile.acquisition["ElectricalSeries"]
        electrodes = nwbfile.electrodes.to_dataframe()
        summary = {
            "identifier": nwbfile.identifier,
            "session_id": nwbfile.session_id,
            "session_description": nwbfile.session_description,
            "session_start_time": nwbfile.session_start_time.isoformat(),
            "lab": nwbfile.lab,
            "institution": nwbfile.institution,
            "keywords": list(nwbfile.keywords[:]),
            "notes": nwbfile.notes,
            "subject": {
                "subject_id": nwbfile.subject.subject_id,
                "species": nwbfile.subject.species,
                "sex": nwbfile.subject.sex,
                "age": nwbfile.subject.age,
                "description": nwbfile.subject.description,
            },
            "devices": sorted(nwbfile.devices),
            "electrode_groups": {name: group.location for name, group in nwbfile.electrode_groups.items()},
            "electrodes": {
                "group_name": list(electrodes["group_name"]),
                "location": list(electrodes["location"]),
                "channel_name": list(electrodes["channel_name"]),
                "headstage_channel": [int(value) for value in electrodes["headstage_channel"]],
                "reference_electrode": [bool(value) for value in electrodes["reference_electrode"]],
            },
            "electrical_series": {
                "shape": list(series.data.shape),
                "dtype": str(series.data.dtype),
                "rate": series.rate,
                "starting_time": series.starting_time,
                "conversion": series.conversion,
                "data_sha256": _sha256(series.data[:]),
            },
            "videos": {
                name: {
                    "external_file": list(item.external_file[:]),
                    "num_samples": int(item.num_samples),
                    "rate": item.rate,
                    "starting_time": item.starting_time,
                    "device": item.device.name,
                }
                for name, item in nwbfile.acquisition.items()
                if isinstance(item, pynwb.image.ImageSeries)
            },
        }
    return summary


def summarize_output_tree(output_dir, /):
    """Every NWB file's summary keyed by its path relative to *output_dir*, plus the full file listing."""
    output_dir = Path(output_dir)
    files = sorted(str(path.relative_to(output_dir)) for path in output_dir.rglob("*") if path.is_file())
    summaries = {str(path.relative_to(output_dir)): summarize_nwb(path) for path in sorted(output_dir.rglob("*.nwb"))}
    tree = {"files": files, "nwb": summaries}
    return tree
