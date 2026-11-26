"""Integration tests for ``code/convert_luc3d_to_bids.py``.

Runs the converter on the committed mock of dandiset 000641 (``tests/example_raw/``) and compares the
study it writes against the committed golden tree (``tests/expected_output/<dataset>/``).

``ffprobe`` is provided by the PyAV-backed ``tests/ffprobe_shim.py``, so the run needs no system FFmpeg.
Regenerate the fixtures after an intended change with ``python3 tests/generate_fixtures.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "code"))

import convert_luc3d_to_bids as conv  # noqa: E402

pytestmark = pytest.mark.ai_generated

EXAMPLE_RAW = TESTS / "example_raw"
EXPECTED_OUTPUT = TESTS / "expected_output"
SHIM = TESTS / "ffprobe_shim.py"
CONFIG = TESTS.parent / "code" / "config.yaml"
DATASETS = ["mouse-dyad-10m", "slap-2m"]


def relative_files(root: Path, /) -> set[str]:
    files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    return files


def convert(*, dataset: str, output: Path, incoming: Path = EXAMPLE_RAW, **options) -> int:
    exit_code = conv.convert_dataset(
        incoming_dir=incoming,
        standardized_dir=output,
        config_path=CONFIG,
        dataset_key=dataset,
        ffprobe_bin=str(SHIM),
        **options,
    )
    return exit_code


@pytest.mark.parametrize("dataset", DATASETS)
def test_conversion_matches_expected_output(dataset, tmp_path):
    expected_root = EXPECTED_OUTPUT / dataset
    output = tmp_path / dataset

    exit_code = convert(dataset=dataset, output=output)

    assert exit_code == 0
    assert relative_files(output) == relative_files(expected_root)
    for relative in sorted(relative_files(expected_root)):
        produced, expected = output / relative, expected_root / relative
        if relative.endswith(".json"):
            assert json.loads(produced.read_text()) == json.loads(expected.read_text()), relative
        else:
            assert produced.read_bytes() == expected.read_bytes(), relative


@pytest.mark.parametrize("dataset", DATASETS)
def test_second_run_skips_converted_sessions(dataset, tmp_path, capsys):
    output = tmp_path / dataset
    convert(dataset=dataset, output=output)
    before = {relative: (output / relative).read_bytes() for relative in relative_files(output)}
    capsys.readouterr()

    exit_code = convert(dataset=dataset, output=output)

    assert exit_code == 0
    assert "0 converted" in capsys.readouterr().out
    after = {relative: (output / relative).read_bytes() for relative in relative_files(output)}
    assert after == before


@pytest.mark.parametrize("dataset", DATASETS)
def test_out_of_scope_files_are_reported(dataset, tmp_path, capsys):
    convert(dataset=dataset, output=tmp_path / dataset)

    report = capsys.readouterr().out

    expected = {"mouse-dyad-10m": "sessions/20250908_152229/notes.txt", "slap-2m": ".slpanalysis.h5"}
    assert expected[dataset] in report


def test_frame_count_disagreeing_with_lab_table_is_reported(tmp_path, capsys):
    convert(dataset="mouse-dyad-10m", output=tmp_path / "out")

    report = capsys.readouterr().out

    assert "22085397-20250827141804.mp4: 5 frames, the lab's qc_views.csv says 6" in report


def test_empty_incoming_dandiset_exits_cleanly(tmp_path):
    results = tmp_path / "results.json"

    exit_code = convert(dataset="slap-2m", output=tmp_path / "out", incoming=tmp_path / "empty", results_path=results)

    assert exit_code == 0
    assert json.loads(results.read_text()) == {"pending": {}, "failed": {}}


def test_session_without_3d_file_is_pending(tmp_path):
    session = tmp_path / "in" / "sourcedata/raw/luc3d/MouseDyad-10M/sessions/20250101_000000"
    session.mkdir(parents=True)
    results = tmp_path / "results.json"

    exit_code = convert(
        dataset="mouse-dyad-10m", output=tmp_path / "out", incoming=tmp_path / "in", results_path=results
    )

    assert exit_code == 1
    assert list(json.loads(results.read_text())["pending"]) == ["20250101_000000"]


def test_session_the_lab_excluded_is_not_converted(tmp_path, capsys):
    session = tmp_path / "in" / "sourcedata/raw/luc3d/MouseDyad-10M/sessions/20250904_183921"
    session.mkdir(parents=True)

    exit_code = convert(dataset="mouse-dyad-10m", output=tmp_path / "out", incoming=tmp_path / "in")

    assert exit_code == 0
    assert "excluded [20250904_183921]" in capsys.readouterr().out
    assert list((tmp_path / "out" / "rawbids").glob("sub-*")) == []


@pytest.mark.parametrize(
    ("function", "folder", "expected"),
    [
        (conv.dyad_session_label, "20250827_141755", "20250827141755"),
        (conv.slap_session_label, "10072022120554", "20221007120554"),
        (conv.dyad_subject_label, ["181321", "181313"], "181313x181321"),
        (conv.dyad_subject_label, ["181313", "181321"], "181313x181321"),
        (conv.iso_from_label, "20250827141804", "2025-08-27T14:18:04"),
    ],
)
def test_identity_rules(function, folder, expected):
    assert function(folder) == expected
