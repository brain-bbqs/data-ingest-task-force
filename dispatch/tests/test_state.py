import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dispatch/

from state import STATE_FILENAME, IngestState, hash_file  # noqa: E402

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
