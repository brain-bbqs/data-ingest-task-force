import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dispatch/

from state import STATE_FILENAME, IngestState, hash_file, manifest_filename  # noqa: E402

pytestmark = pytest.mark.ai_generated


def test_load_missing_manifest_returns_empty_state(tmp_path):
    state = IngestState.load(tmp_path)
    assert state.script_sha256 is None
    assert state.converted_sessions == {}
    assert state.new_sessions(["ses-1", "ses-2"]) == ["ses-1", "ses-2"]


def test_save_then_load_round_trips(tmp_path):
    state = IngestState()
    state.mark_converted("ses-1", source_path="/incoming/000001/raw/ses-1", converted_at="2026-08-06T00:00:00+00:00")
    state.script_sha256 = "deadbeef"
    state.last_run_at = "2026-08-06T00:00:00+00:00"
    state.save(tmp_path)

    assert (tmp_path / STATE_FILENAME).is_file()

    reloaded = IngestState.load(tmp_path)
    assert reloaded.script_sha256 == "deadbeef"
    assert reloaded.converted_sessions.keys() == {"ses-1"}
    assert reloaded.last_run_at == "2026-08-06T00:00:00+00:00"


def test_new_sessions_excludes_already_converted():
    state = IngestState()
    state.mark_converted("ses-1", source_path="x", converted_at="t")
    assert state.new_sessions(["ses-1", "ses-2"]) == ["ses-2"]


def test_hash_file_is_stable_and_sensitive_to_content(tmp_path):
    f = tmp_path / "script.py"
    f.write_text("print('a')\n")
    first = hash_file(f)
    assert first == hash_file(f)

    f.write_text("print('b')\n")
    assert hash_file(f) != first


def test_manifest_filename_unshared_keeps_the_bare_name():
    assert manifest_filename("suthana/in-lab", shared=False) == STATE_FILENAME


def test_manifest_filename_shared_is_unique_per_project_key():
    assert manifest_filename("suthana/in-lab", shared=True) == ".ingest_state.suthana__in-lab.json"
    assert manifest_filename("suthana/seeber-2024", shared=True) == ".ingest_state.suthana__seeber-2024.json"


def test_shared_manifests_do_not_collide(tmp_path):
    one = IngestState(script_sha256="hash-one")
    one.mark_converted("ses-1", source_path="x", converted_at="t")
    two = IngestState(script_sha256="hash-two")
    two.mark_converted("Seeber_etal_2024_data_code", source_path="y", converted_at="t")

    one.save(tmp_path, manifest_name=manifest_filename("a/one", shared=True))
    two.save(tmp_path, manifest_name=manifest_filename("a/two", shared=True))

    reloaded_one = IngestState.load(tmp_path, manifest_name=manifest_filename("a/one", shared=True))
    reloaded_two = IngestState.load(tmp_path, manifest_name=manifest_filename("a/two", shared=True))
    assert reloaded_one.script_sha256 == "hash-one"
    assert reloaded_two.script_sha256 == "hash-two"
    assert reloaded_one.converted_sessions.keys() == {"ses-1"}
    assert reloaded_two.converted_sessions.keys() == {"Seeber_etal_2024_data_code"}
