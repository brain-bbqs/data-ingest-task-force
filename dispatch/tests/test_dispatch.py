import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dispatch/

from registry import Project  # noqa: E402
from sessions import SessionSpec  # noqa: E402
from state import IngestState  # noqa: E402

import dispatch  # noqa: E402

pytestmark = pytest.mark.ai_generated

SESSION_SPEC = SessionSpec(include=["raw/*"])


def make_project(**overrides) -> Project:
    defaults = dict(
        lab="test-lab",
        incoming_dandiset_id="000001",
        standardized_dandiset_id="000002",
        script_path="labs/test-lab/code/convert.py",
        convert_command=[
            "python3",
            "{repo_root}/labs/test-lab/code/convert.py",
            "{incoming_dir}",
            "{standardized_dir}",
        ],
        overwrite_flag="--overwrite",
    )
    defaults.update(overrides)
    return Project(**defaults)


def make_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    script = repo_root / "labs" / "test-lab" / "code" / "convert.py"
    script.parent.mkdir(parents=True)
    script.write_text("# v1\n")
    return repo_root


def test_process_project_converts_new_sessions_and_records_state(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    calls = []
    monkeypatch.setattr(dispatch.subprocess, "run", lambda cmd, cwd=None, check=True: calls.append((cmd, cwd)))

    project = make_project()
    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )

    # download skipped + upload skipped -> only the conversion command ran.
    assert len(calls) == 1
    cmd, cwd = calls[0]
    assert cmd[0] == "python3"
    assert str(repo_root / "labs" / "test-lab" / "code" / "convert.py") in cmd
    assert str(incoming_root / "000001") in cmd
    assert str(standardized_root / "000002") in cmd
    # First-ever run: no manifest yet, so "script hash changed" is trivially
    # true (None -> real hash) and dispatch reprocesses with --overwrite.
    assert "--overwrite" in cmd

    state = IngestState.load(standardized_root / "000002")
    assert set(state.converted_sessions) == {"ses-1"}
    assert state.converted_sessions["ses-1"]["source_path"] == str(incoming_root / "000001" / "raw" / "ses-1")
    assert state.script_sha256 is not None


def test_process_project_skips_when_nothing_new(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    project = make_project()
    script_hash = dispatch.hash_file(project.script_abspath(repo_root))
    state_dir = standardized_root / "000002"
    state = IngestState(script_sha256=script_hash)
    state.mark_converted("ses-1", source_path="x", converted_at="t")
    state.save(state_dir)

    calls = []
    monkeypatch.setattr(dispatch.subprocess, "run", lambda cmd, cwd=None, check=True: calls.append((cmd, cwd)))

    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )
    assert calls == []  # no conversion, no upload


def test_process_project_forces_overwrite_when_script_changes(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    project = make_project()
    state_dir = standardized_root / "000002"
    state = IngestState(script_sha256="stale-hash")
    state.mark_converted("ses-1", source_path="x", converted_at="t")
    state.save(state_dir)

    calls = []
    monkeypatch.setattr(dispatch.subprocess, "run", lambda cmd, cwd=None, check=True: calls.append((cmd, cwd)))

    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )
    assert len(calls) == 1
    assert "--overwrite" in calls[0][0]

    reloaded = IngestState.load(state_dir)
    assert reloaded.script_sha256 == dispatch.hash_file(project.script_abspath(repo_root))


def test_dry_run_makes_no_filesystem_or_subprocess_changes(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    calls = []
    monkeypatch.setattr(dispatch.subprocess, "run", lambda cmd, cwd=None, check=True: calls.append((cmd, cwd)))

    project = make_project()
    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        skip_download=False,
        skip_upload=False,
        dry_run=True,
    )
    assert calls == []
    assert not (standardized_root / "000002").exists()
