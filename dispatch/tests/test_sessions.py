import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dispatch/

from sessions import SessionSpec, SessionSpecError, discover_sessions, load_session_specs  # noqa: E402

pytestmark = pytest.mark.ai_generated


def test_load_session_specs_reads_the_committed_sessions_json():
    specs = load_session_specs(Path(__file__).resolve().parents[1] / "sessions.json")
    assert specs["kemere"].include == ["sourcedata/raw/*-Session*"]
    assert specs["kemere"].exclude == []


def test_load_session_specs_requires_non_empty_include(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps({"labs": {"test-lab": {"include": []}}}))
    with pytest.raises(SessionSpecError, match="include"):
        load_session_specs(path)


def test_load_session_specs_rejects_no_labs(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps({"labs": {}}))
    with pytest.raises(SessionSpecError, match="no labs"):
        load_session_specs(path)


def test_discover_sessions_matches_directories_only(tmp_path):
    (tmp_path / "raw" / "ses-1").mkdir(parents=True)
    (tmp_path / "raw" / "ses-2").mkdir(parents=True)
    (tmp_path / "raw" / "notes.txt").write_text("x")

    spec = SessionSpec(include=["raw/*"])
    assert [p.name for p in discover_sessions(tmp_path, spec)] == ["ses-1", "ses-2"]


def test_discover_sessions_unions_multiple_include_patterns(tmp_path):
    (tmp_path / "raw" / "ses-1").mkdir(parents=True)
    (tmp_path / "extra" / "ses-2").mkdir(parents=True)

    spec = SessionSpec(include=["raw/*", "extra/*"])
    assert [p.name for p in discover_sessions(tmp_path, spec)] == ["ses-1", "ses-2"]


def test_discover_sessions_applies_exclude_by_basename(tmp_path):
    (tmp_path / "raw" / "ses-1").mkdir(parents=True)
    (tmp_path / "raw" / "ses-1-ignore").mkdir(parents=True)

    spec = SessionSpec(include=["raw/*"], exclude=["*-ignore"])
    assert [p.name for p in discover_sessions(tmp_path, spec)] == ["ses-1"]


def test_discover_sessions_applies_exclude_by_relative_path(tmp_path):
    (tmp_path / "raw" / "ses-1").mkdir(parents=True)
    (tmp_path / "raw" / "tmp-ses-2").mkdir(parents=True)

    spec = SessionSpec(include=["raw/*"], exclude=["raw/tmp-*"])
    assert [p.name for p in discover_sessions(tmp_path, spec)] == ["ses-1"]


def test_load_session_specs_accepts_a_lab_slash_project_key(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps({"labs": {"test-lab/in-lab": {"include": ["raw/*"]}}}))
    specs = load_session_specs(path)
    assert specs["test-lab/in-lab"].include == ["raw/*"]

