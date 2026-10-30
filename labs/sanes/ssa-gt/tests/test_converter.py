"""End-to-end and unit tests for the SSA GT converter and its batch driver.

The experiment is synthesized in a temporary directory from the source layout the lab described: two
``idx_*`` chunks with per-channel WAV files, one MP4, one tracks CSV and one annotations CSV each, plus
the experiment log. FFmpeg must be on PATH to write and concatenate the videos.
"""

import csv
import subprocess
import sys
from pathlib import Path

import h5py
import numpy
import pynwb
import pytest
import scipy.io.wavfile
import yaml

CODE = Path(__file__).resolve().parents[1] / "code"
sys.path.insert(0, str(CODE))

import _sanes_ssa_gt_to_nwb as converter  # noqa: E402
import batch_convert  # noqa: E402

AUDIO_RATE = 1000
VIDEO_RATE = 10
CHUNK_SAMPLES = (500, 300)
CHUNK_FRAMES = (5, 3)
CHANNELS = 2


def _write_rows(*, path, fieldnames, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_experiment(*, root, number):
    experiment = root / f"experiment_{number}"
    experiment.mkdir(parents=True)
    (experiment / f"experiment_{number}_log_2025-08-12_11-01-09.txt").write_text(
        "2025-08-12_11-01-05>Initializing\n2025-08-12_11-01-09>Started Experiment Now\n"
    )
    for index, (samples, frames) in enumerate(zip(CHUNK_SAMPLES, CHUNK_FRAMES)):
        chunk = experiment / f"idx_{index:03d}"
        chunk.mkdir()
        for channel in range(CHANNELS):
            data = numpy.full(samples, fill_value=index + channel / 10, dtype=numpy.float32)
            scipy.io.wavfile.write(chunk / f"channel_{channel:02d}_file_{index:03d}.wav", AUDIO_RATE, data)
        video_name = f"video_gily_center_{index:03d}.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size=32x32:rate={VIDEO_RATE}"]
            + ["-frames:v", str(frames), "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(chunk / video_name)],
            check=True,
        )
        _write_rows(
            path=chunk / f"{index:03d}_video_gily_center_{index:03d}.tracks.csv",
            fieldnames=["track", "frame_idx", "instance.score", "nose.x", "nose.y", "nose.score"],
            rows=[
                {"track": "track_0", "frame_idx": 0, "instance.score": 0.9, "nose.x": 1.0, "nose.y": 2.0},
                {"track": "track_0", "frame_idx": 2, "instance.score": 0.9, "nose.x": "", "nose.y": 3.0},
                {"track": "track_1", "frame_idx": 1, "instance.score": 0.8, "nose.x": 4.0, "nose.y": 5.0},
            ],
        )
        _write_rows(
            path=chunk / f"exp_{number}_idx_{index:03d}_ch_03_08_annotations.csv",
            fieldnames=["name", "start_seconds", "stop_seconds", "channel"],
            rows=[
                {"name": "chirp", "start_seconds": 0.1, "stop_seconds": 0.15, "channel": 3},
                {"name": "incomplete", "start_seconds": "", "stop_seconds": 0.2, "channel": 8},
            ],
        )
    return experiment


@pytest.fixture(scope="module")
def converted(tmp_path_factory):
    incoming = tmp_path_factory.mktemp("incoming") / "ssa_gt_data"
    _write_experiment(root=incoming, number=280)
    standardized = tmp_path_factory.mktemp("standardized")
    batch_convert.convert_batch(incoming_dir=incoming, standardized_dir=standardized, config_path=CODE / "config.yaml")
    return standardized


@pytest.mark.ai_generated
def test_output_layout(converted):
    actual = sorted(str(path.relative_to(converted)) for path in converted.rglob("*") if path.is_file())
    expected = [
        "sub-00/sub-00_ses-experiment280.nwb",
        "sub-01/sub-01_ses-experiment280.nwb",
        "sub-multi/sub-multi_ses-experiment280_behavior.nwb",
        "sub-multi/sub-multi_ses-experiment280_video.mp4",
    ]
    assert actual == expected


@pytest.mark.ai_generated
def test_multisubject_file(converted):
    path = converted / "sub-multi" / "sub-multi_ses-experiment280_behavior.nwb"
    with pynwb.NWBHDF5IO(path, "r") as io:
        nwbfile = io.read()
        assert nwbfile.identifier == "sanes-ssa-gt-experiment_280"
        assert nwbfile.session_start_time.isoformat() == "2025-08-12T11:01:09+00:00"
        assert nwbfile.session_description == "SSL dropped mic setup with 10 microphones"

        audio = nwbfile.acquisition["Multi-channel Acoustic Data"]
        assert audio.data.shape == (sum(CHUNK_SAMPLES), CHANNELS)
        assert audio.rate == AUDIO_RATE
        assert audio.data[CHUNK_SAMPLES[0], 1] == pytest.approx(1.1)

        video = nwbfile.acquisition["External Behavioral Video (Combined)"]
        assert list(video.external_file[:]) == ["sub-multi_ses-experiment280_video.mp4"]
        assert video.rate == VIDEO_RATE

        behavior = nwbfile.processing["behavior"]
        tracking = behavior["tracking_track0"]
        assert tracking.timestamps[:].tolist() == pytest.approx([0.0, 0.2, 0.5, 0.7])
        assert numpy.isnan(tracking.data[1, 0])

        events = behavior["vocalizations"].to_dataframe()
        assert events["timestamp"].tolist() == pytest.approx([0.1, 0.6])
        assert events["duration"].tolist() == pytest.approx([0.05, 0.05])
        assert events["label"].tolist() == ["chirp", "chirp"]

        subjects = nwbfile.subjects_table.to_dataframe()
        assert subjects["subject_id"].tolist() == ["00", "01"]
        links = subjects["individual_subj_link"].tolist()
        assert links == ["../sub-00/sub-00_ses-experiment280.nwb", "../sub-01/sub-01_ses-experiment280.nwb"]
        assert all((path.parent / link).is_file() for link in links)

    with h5py.File(path, "r") as file:
        assert file["acquisition/Multi-channel Acoustic Data/data"].compression == "gzip"


@pytest.mark.ai_generated
@pytest.mark.parametrize(
    ("subject", "track", "timestamps"), [("00", "track_0", [0.0, 0.2, 0.5, 0.7]), ("01", "track_1", [0.1, 0.6])]
)
def test_track_files(converted, subject, track, timestamps):
    path = converted / f"sub-{subject}" / f"sub-{subject}_ses-experiment280.nwb"
    with pynwb.NWBHDF5IO(path, "r") as io:
        nwbfile = io.read()
        assert nwbfile.subject.subject_id == subject
        assert track in nwbfile.subject.description
        assert nwbfile.processing["behavior"]["tracking"].timestamps[:].tolist() == pytest.approx(timestamps)


@pytest.mark.ai_generated
def test_existing_output_is_skipped_without_overwrite(converted, tmp_path, capsys):
    incoming = tmp_path / "incoming"
    _write_experiment(root=incoming, number=280)
    batch_convert.convert_batch(incoming_dir=incoming, standardized_dir=converted, config_path=CODE / "config.yaml")
    assert "Exists, skipping" in capsys.readouterr().out


@pytest.mark.ai_generated
@pytest.mark.parametrize("nesting", ["", "dataset_folder"])
def test_discover_experiments(tmp_path, nesting):
    parent = tmp_path / nesting
    for name in ("experiment_281", "experiment_280"):
        (parent / name).mkdir(parents=True)
    (parent / "experiment_notes.txt").write_text("")
    actual = [path.name for path in batch_convert.discover_experiments(tmp_path)]
    assert actual == ["experiment_280", "experiment_281"]


@pytest.mark.ai_generated
@pytest.mark.parametrize(
    ("config_name", "expected"),
    [
        ("config.yaml", "SSL dropped mic setup with 10 microphones"),
        ("config_big_arena_2024_12.yaml", None),
        ("config_big_arena_2025_03.yaml", None),
    ],
)
def test_experiment_description_per_dataset(config_name, expected):
    config_path = CODE / config_name
    cfg = yaml.safe_load(config_path.read_text())
    metadata = converter._experiment_metadata(experiment_dir=Path("experiment_280"), config_path=config_path, cfg=cfg)
    actual = metadata.get("description")
    assert actual == expected


@pytest.mark.ai_generated
@pytest.mark.parametrize(("value", "expected"), [("experiment_280", "experiment280"), ("track 1", "track1"), ("", "")])
def test_sanitize_label(value, expected):
    actual = converter.sanitize_label(value)
    assert actual == expected
