#!/usr/bin/env python3
"""Generate the committed mock input fixture for the integration test.

Writes ``tests/example_raw/S1_aligned_data.mat`` and the companion
``tests/example_raw/Trajectories_runtimes.csv``: a tiny but structurally
faithful stand-in for one subject's aligned in-lab recording (see
``code/README.md`` for the real data layout). All values are deterministic
so regenerating the fixture is reproducible.

The real files are MATLAB v7.3, which is HDF5, so the fixture is written
with h5py directly. Two MATLAB-specific encodings have to be reproduced by
hand for the converter to read it the same way it reads a real file: char
arrays are stored as arrays of UTF-16 code units, and cell arrays are stored
as arrays of HDF5 object references into a separate ``#refs#`` group.

Run with::

    python3 tests/generate_fixtures.py
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy

TESTS = Path(__file__).resolve().parent
EXAMPLE_RAW = TESTS / "example_raw"

MAT_FILENAME = "S1_aligned_data.mat"
RUNTIMES_FILENAME = "Trajectories_runtimes.csv"

SUBJECT_ID = "R056"
PAPER_ID = "S1"

SAMPLE_RATE = 10.0
SAMPLE_COUNT = 40
SEGMENT_COUNT = 2

IEEG_CHANNEL_COUNT = 4
SCALP_CHANNEL_COUNT = 63
POSITION_ROW_COUNT = 10
HEAD_ROTATION_ROW_COUNT = 3

# Must stay in sync with the segment start times the test asserts on.
SEGMENT_START_TIMES = ["2024-06-01 09:00:00", "2024-06-01 09:30:00"]

HEAD_ROTATION_LABELS = ["yaw", "pitch", "roll"]
POSITION_LABELS = [
    "hip_x",
    "hip_y",
    "left_leg_x",
    "left_leg_y",
    "left_leg_z",
    "right_leg_x",
    "right_leg_y",
    "right_leg_z",
    "head_x",
    "head_y",
]
SCALP_LABELS = [f"ch{index:02d}" for index in range(SCALP_CHANNEL_COUNT)]

BEEP_OBJECTS = [["lamp", "chair"], ["door"]]
BEEP_INDICES = [[5, 21], [9]]
BUTTON_RESPONSES = [["LeftButton", "MidButton"], ["RightButton"]]
BUTTON_INDICES = [[7, 25], [13]]
BUTTON_SCORES = [[1, 2], [1]]
BUTTON_ATTEMPTS = [[1, 2], [1]]
BUTTON_CORRECT = [[1, -1], [1]]


class RefStore:
    """Writes values into ``#refs#`` and hands back HDF5 object references.

    MATLAB stores the contents of a cell array this way: the cell array
    itself is an array of references, and each referenced object lives under
    the file's ``#refs#`` group.
    """

    def __init__(self, mat_file, /):
        self.mat_file = mat_file
        self.group = mat_file.create_group("#refs#")
        self.counter = 0

    def _next_name(self):
        name = f"r{self.counter:04d}"
        self.counter += 1
        return name

    def dataset(self, values, /):
        """Store *values* as a dataset and return a reference to it."""
        stored = self.group.create_dataset(self._next_name(), data=values)
        return stored.ref

    def string(self, text, /):
        """Store *text* the way MATLAB stores a char array."""
        codes = numpy.array([ord(character) for character in text], dtype=numpy.uint16)
        return self.dataset(codes)

    def subgroup(self):
        """Create an empty group under ``#refs#`` and return it."""
        created = self.group.create_group(self._next_name())
        return created


def _labelled_entry(*, refs, data, labels):
    """A recording entry shaped like MATLAB's ``struct`` with data + hdr.

    ``hdr`` is an (nrows, 2) reference array whose second column holds the
    per-row label strings; the converter reads labels from that column.
    """
    entry = refs.subgroup()
    entry.create_dataset("data", data=data)
    header = numpy.empty((len(labels), 2), dtype=h5py.ref_dtype)
    for index, label in enumerate(labels):
        header[index, 0] = refs.string("")
        header[index, 1] = refs.string(label)
    entry.create_dataset("hdr", data=header)
    return entry


def _ramp(*, rows, columns, scale):
    """A deterministic (rows, columns) float matrix."""
    values = numpy.arange(rows * columns, dtype=numpy.float64).reshape(rows, columns) * scale
    return values


def _segment_sample_count(segment, /):
    """Segments deliberately differ in length, as the real ones do."""
    count = SAMPLE_COUNT - segment * 4
    return count


def _build_events(*, refs, segment):
    entry = refs.subgroup()

    beep = numpy.empty((2, len(BEEP_INDICES[segment])), dtype=h5py.ref_dtype)
    for column, (index, obj) in enumerate(zip(BEEP_INDICES[segment], BEEP_OBJECTS[segment])):
        beep[0, column] = refs.dataset(numpy.array([[float(index)]]))
        beep[1, column] = refs.string(obj)
    entry.create_dataset("beep", data=beep)

    button_rows = [
        BUTTON_INDICES[segment],
        BUTTON_RESPONSES[segment],
        BUTTON_SCORES[segment],
        BUTTON_ATTEMPTS[segment],
        BUTTON_CORRECT[segment],
    ]
    button = numpy.empty((5, len(BUTTON_INDICES[segment])), dtype=h5py.ref_dtype)
    for row, values in enumerate(button_rows):
        for column, value in enumerate(values):
            if isinstance(value, str):
                button[row, column] = refs.string(value)
            else:
                button[row, column] = refs.dataset(numpy.array([[float(value)]]))
    entry.create_dataset("button", data=button)

    return entry


def build_mat(path, /):
    with h5py.File(path, "w") as mat_file:
        refs = RefStore(mat_file)
        trajectories = mat_file.create_group("Trajectories")
        trajectories.create_dataset("Fs", data=numpy.array([[SAMPLE_RATE]]))
        trajectories.create_dataset(
            "Subject_ID",
            data=numpy.array([[ord(character)] for character in SUBJECT_ID], dtype=numpy.uint16),
        )
        recordings = trajectories.create_group("recordings")

        entries = {
            name: numpy.empty((SEGMENT_COUNT, 1), dtype=h5py.ref_dtype)
            for name in ("gaze", "head_rotation", "position", "iEEG", "scalp_EEG", "events")
        }

        for segment in range(SEGMENT_COUNT):
            samples = _segment_sample_count(segment)

            entries["gaze"][segment, 0] = refs.dataset(_ramp(rows=2, columns=samples, scale=1.0))

            head_rotation = _labelled_entry(
                refs=refs,
                data=_ramp(rows=HEAD_ROTATION_ROW_COUNT, columns=samples, scale=0.01),
                labels=HEAD_ROTATION_LABELS,
            )
            entries["head_rotation"][segment, 0] = head_rotation.ref

            position = _labelled_entry(
                refs=refs,
                data=_ramp(rows=POSITION_ROW_COUNT, columns=samples, scale=0.1),
                labels=POSITION_LABELS,
            )
            entries["position"][segment, 0] = position.ref

            ieeg = refs.subgroup()
            ieeg.create_dataset("data", data=_ramp(rows=IEEG_CHANNEL_COUNT, columns=samples, scale=2.0))
            ieeg.create_dataset(
                "ix_IED",
                data=(_ramp(rows=IEEG_CHANNEL_COUNT, columns=samples, scale=1.0) % 7 == 0),
            )
            entries["iEEG"][segment, 0] = ieeg.ref

            scalp = refs.subgroup()
            scalp.create_dataset("data", data=_ramp(rows=SCALP_CHANNEL_COUNT, columns=samples, scale=3.0))
            scalp.create_dataset(
                "ix_art",
                data=(_ramp(rows=SCALP_CHANNEL_COUNT, columns=samples, scale=1.0) % 11 == 0),
            )
            channel_labels = numpy.empty((1, SCALP_CHANNEL_COUNT), dtype=h5py.ref_dtype)
            for index, label in enumerate(SCALP_LABELS):
                channel_labels[0, index] = refs.string(label)
            scalp.create_dataset("chan_labels", data=channel_labels)
            entries["scalp_EEG"][segment, 0] = scalp.ref

            entries["events"][segment, 0] = _build_events(refs=refs, segment=segment).ref

        for name, references in entries.items():
            recordings.create_dataset(name, data=references)


def build_runtimes(path, /):
    header = f"Subject_{PAPER_ID}_runtimes"
    lines = [header, *SEGMENT_START_TIMES]
    path.write_text("\n".join(lines) + "\n")


def main():
    EXAMPLE_RAW.mkdir(parents=True, exist_ok=True)
    mat_path = EXAMPLE_RAW / MAT_FILENAME
    runtimes_path = EXAMPLE_RAW / RUNTIMES_FILENAME
    build_mat(mat_path)
    build_runtimes(runtimes_path)
    print(f"Wrote {mat_path}")
    print(f"Wrote {runtimes_path}")


if __name__ == "__main__":
    main()
