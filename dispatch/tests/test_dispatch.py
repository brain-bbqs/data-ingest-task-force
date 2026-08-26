import json
import subprocess
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
DANDI_IMAGE = "ghcr.io/example/dandi-cli:test"


def dandi_listing(*asset_paths: str) -> str:
    """`dandi ls --format json_lines` output: the dandiset-level record the
    real listing leads with, then one record per asset."""
    records = [{"path": "000001", "version": "draft", "size": 1, "modified": "2026-01-01T00:00:00Z"}]
    records += [
        {"asset_id": f"asset-{index}", "path": path, "size": 10, "modified": "2026-01-01T00:00:00Z"}
        for index, path in enumerate(asset_paths)
    ]
    return "".join(json.dumps(record) + "\n" for record in records)


DEFAULT_LISTING = dandi_listing("raw/ses-1/data.nwb")


def record_subprocess(monkeypatch, calls, *, listing: str = DEFAULT_LISTING) -> list[list[str]]:
    """Stub subprocess.run for both of dispatch's callers.

    Acting commands (run) land in *calls*; the read-only listing query
    (run_captured, the only caller passing capture_output) is returned
    separately so it never inflates a test's count of side effects.
    """
    listing_calls: list[list[str]] = []

    def fake_run(cmd, cwd=None, check=True, capture_output=False, text=False):
        if capture_output:
            listing_calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout=listing, stderr="")
        calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(dispatch.subprocess, "run", fake_run)
    return listing_calls


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
    record_subprocess(monkeypatch, calls)

    project = make_project()
    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
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
    record_subprocess(monkeypatch, calls)

    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )
    assert calls == []  # no conversion, no upload


def test_process_project_nothing_new_skips_upload_even_when_enabled(tmp_path, monkeypatch):
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
    record_subprocess(monkeypatch, calls)

    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=False,
        dry_run=False,
    )
    assert calls == []  # upload enabled, but nothing new -> nothing runs


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
    record_subprocess(monkeypatch, calls)

    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )
    assert len(calls) == 1
    assert "--overwrite" in calls[0][0]

    reloaded = IngestState.load(state_dir)
    assert reloaded.script_sha256 == dispatch.hash_file(project.script_abspath(repo_root))


def test_unchanged_listing_skips_the_download_entirely(tmp_path, monkeypatch):
    """The point of the whole fingerprint: a pass with nothing new upstream
    must not pay for `dandi download`, which re-transfers the dandiset in full
    whenever refresh's mtime check cannot skip."""
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    project = make_project()
    state = IngestState(
        script_sha256=dispatch.hash_file(project.script_abspath(repo_root)),
        remote_listing_sha256=dispatch.remote_listing_fingerprint_from_output(DEFAULT_LISTING),
    )
    state.mark_converted("ses-1", source_path="x", converted_at="t")
    state.save(standardized_root / "000002")

    calls = []
    record_subprocess(monkeypatch, calls)

    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
        skip_download=False,  # download enabled, and still must not run
        skip_upload=False,
        dry_run=False,
    )
    assert calls == []


def test_first_no_op_pass_records_the_listing_so_the_next_one_can_skip(tmp_path, monkeypatch):
    """A pass that downloads and finds nothing new still has to bank the
    fingerprint, or the gate never has a baseline and every pass downloads."""
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    project = make_project()
    state = IngestState(script_sha256=dispatch.hash_file(project.script_abspath(repo_root)))
    state.mark_converted("ses-1", source_path="x", converted_at="t")
    state.save(standardized_root / "000002")

    calls = []
    record_subprocess(monkeypatch, calls)
    kwargs = dict(
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
        skip_download=False,
        skip_upload=True,
        dry_run=False,
    )

    dispatch.process_project(project, **kwargs)
    assert [cmd for cmd, _ in calls if "download" in cmd]  # this pass paid for one

    reloaded = IngestState.load(standardized_root / "000002")
    assert reloaded.remote_listing_sha256 is not None

    calls.clear()
    dispatch.process_project(project, **kwargs)
    assert calls == []  # the next one does not


def test_new_asset_upstream_reopens_the_gate(tmp_path, monkeypatch):
    """A changed listing must fall through to the download, or genuinely new
    sessions would never be picked up."""
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    project = make_project()
    state = IngestState(
        script_sha256=dispatch.hash_file(project.script_abspath(repo_root)),
        remote_listing_sha256=dispatch.remote_listing_fingerprint_from_output(DEFAULT_LISTING),
    )
    state.mark_converted("ses-1", source_path="x", converted_at="t")
    state.save(standardized_root / "000002")

    calls = []
    record_subprocess(
        monkeypatch,
        calls,
        listing=dandi_listing("raw/ses-1/data.nwb", "raw/ses-2/data.nwb"),
    )
    (incoming_root / "000001" / "raw" / "ses-2").mkdir()

    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
        skip_download=False,
        skip_upload=True,
        dry_run=False,
    )
    assert [cmd for cmd, _ in calls if "download" in cmd]
    assert [cmd for cmd, _ in calls if cmd[0] == "python3"]
    assert set(IngestState.load(standardized_root / "000002").converted_sessions) == {"ses-1", "ses-2"}


def test_unlistable_dandiset_falls_back_to_downloading(tmp_path, monkeypatch):
    """A listing that cannot be fetched must never be read as 'nothing new'."""
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    project = make_project()
    state = IngestState(
        script_sha256=dispatch.hash_file(project.script_abspath(repo_root)),
        remote_listing_sha256="whatever-was-recorded-before",
    )
    state.mark_converted("ses-1", source_path="x", converted_at="t")
    state.save(standardized_root / "000002")

    calls = []

    def fake_run(cmd, cwd=None, check=True, capture_output=False, text=False):
        if capture_output:
            raise subprocess.CalledProcessError(1, cmd)
        calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(dispatch.subprocess, "run", fake_run)

    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
        skip_download=False,
        skip_upload=True,
        dry_run=False,
    )
    assert [cmd for cmd, _ in calls if "download" in cmd]


def asset_line(path: str, /, *, asset_id: str = "a1", size: int = 10, modified: str = "2026-01-01T00:00:00Z") -> str:
    return json.dumps({"asset_id": asset_id, "path": path, "size": size, "modified": modified}) + "\n"


DANDISET_LINE = json.dumps({"path": "000001", "version": "draft", "size": 1}) + "\n"


def test_skip_download_never_consults_the_archive(tmp_path, monkeypatch):
    """--skip-download means 'convert what is on disk'. The archive says
    nothing about a session someone put there by hand, so gating on it would
    silently ignore one."""
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)
    (incoming_root / "000001" / "raw" / "ses-2").mkdir()  # dropped in by hand

    project = make_project()
    state = IngestState(
        script_sha256=dispatch.hash_file(project.script_abspath(repo_root)),
        remote_listing_sha256=dispatch.remote_listing_fingerprint_from_output(DEFAULT_LISTING),
    )
    state.mark_converted("ses-1", source_path="x", converted_at="t")
    state.save(standardized_root / "000002")

    calls = []
    listing_calls = record_subprocess(monkeypatch, calls)

    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )
    assert listing_calls == []
    assert [cmd for cmd, _ in calls if cmd[0] == "python3"]
    reloaded = IngestState.load(standardized_root / "000002")
    assert set(reloaded.converted_sessions) == {"ses-1", "ses-2"}
    # The recorded listing still describes the last real download, so a later
    # pass without --skip-download can still trust it.
    assert reloaded.remote_listing_sha256 == state.remote_listing_sha256


def test_missing_docker_falls_back_to_downloading(tmp_path, monkeypatch):
    """A listing query that cannot even start must not take the project down."""
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    calls = []

    def fake_run(cmd, cwd=None, check=True, capture_output=False, text=False):
        if capture_output:
            raise FileNotFoundError(2, "No such file or directory: 'docker'")
        calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(dispatch.subprocess, "run", fake_run)

    dispatch.process_project(
        make_project(),
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
        skip_download=False,
        skip_upload=True,
        dry_run=False,
    )
    assert [cmd for cmd, _ in calls if "download" in cmd]


def test_listing_fingerprint_ignores_asset_order():
    """The API promises no ordering, so a reshuffle must not read as a change."""
    forward = DANDISET_LINE + asset_line("a/x.nwb", asset_id="a1") + asset_line("b/y.nwb", asset_id="a2")
    backward = DANDISET_LINE + asset_line("b/y.nwb", asset_id="a2") + asset_line("a/x.nwb", asset_id="a1")
    assert dispatch.remote_listing_fingerprint_from_output(forward) == (
        dispatch.remote_listing_fingerprint_from_output(backward)
    )


def test_listing_fingerprint_ignores_the_dandiset_record():
    """Only assets decide whether there is new data to convert."""
    with_record = DANDISET_LINE + asset_line("a/x.nwb")
    without_record = asset_line("a/x.nwb")
    assert dispatch.remote_listing_fingerprint_from_output(with_record) == (
        dispatch.remote_listing_fingerprint_from_output(without_record)
    )


@pytest.mark.parametrize(
    "changed",
    [
        pytest.param(asset_line("a/x.nwb", size=11), id="resized"),
        pytest.param(asset_line("a/x.nwb", modified="2026-06-06T00:00:00Z"), id="remodified"),
        pytest.param(asset_line("a/x.nwb", asset_id="a2"), id="replaced"),
        pytest.param(asset_line("a/renamed.nwb"), id="renamed"),
        pytest.param(asset_line("a/x.nwb") + asset_line("b/y.nwb", asset_id="a2"), id="added"),
        pytest.param("", id="emptied"),
    ],
)
def test_listing_fingerprint_changes_when_the_dandiset_does(changed):
    baseline = dispatch.remote_listing_fingerprint_from_output(asset_line("a/x.nwb"))
    assert dispatch.remote_listing_fingerprint_from_output(changed) != baseline


def test_listing_fingerprint_is_none_on_unparsable_output():
    """None means unknown. The caller must never read it as unchanged."""
    assert dispatch.remote_listing_fingerprint_from_output("not json at all\n") is None


def test_dandi_api_key_env_var_follows_dandi_clis_own_naming():
    # dandi-cli's own convention (not this script's) -- there is no single
    # generic DANDI_API_KEY that works for every instance.
    assert dispatch.dandi_api_key_env_var("dandi") == "DANDI_API_KEY"
    assert dispatch.dandi_api_key_env_var("ember-dandi") == "EMBER_DANDI_API_KEY"
    assert dispatch.dandi_api_key_env_var("dandi-sandbox") == "DANDI_SANDBOX_API_KEY"


def test_dandi_download_runs_in_container(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBER_DANDI_API_KEY", "secret-value")
    incoming_root = tmp_path / "incoming"
    incoming_dir = incoming_root / "000001"

    calls = []
    record_subprocess(monkeypatch, calls)

    project = make_project()  # dandi_instance defaults to "ember-dandi"
    dispatch.dandi_download(project, incoming_dir, dandi_image=DANDI_IMAGE, dry_run=False)

    assert len(calls) == 2  # docker pull, then docker run
    pull_cmd, _ = calls[0]
    assert pull_cmd == ["docker", "pull", DANDI_IMAGE]
    run_cmd, _ = calls[1]
    assert run_cmd[:2] == ["docker", "run"]
    assert f"{incoming_root}:{incoming_root}" in run_cmd
    assert "EMBER_DANDI_API_KEY" in run_cmd
    assert not any("secret-value" in token for token in run_cmd)
    assert "DANDI_CACHE=ignore" in run_cmd  # sidesteps a joblib/fscacher digest-cache race
    assert run_cmd[-8:] == [
        DANDI_IMAGE,
        "dandi",
        "download",
        "-o",
        str(incoming_root),
        "-e",
        "refresh",
        "dandi://ember-dandi/000001",
    ]
    assert incoming_root.is_dir()  # created ahead of the mount


def test_dandi_upload_runs_in_container(tmp_path, monkeypatch):
    standardized_dir = tmp_path / "standardized" / "000002"
    standardized_dir.mkdir(parents=True)

    calls = []
    record_subprocess(monkeypatch, calls)

    project = make_project()
    dispatch.dandi_upload(project, standardized_dir, dandi_image=DANDI_IMAGE, dry_run=False)

    assert len(calls) == 3  # docker pull, fetch dandiset.yaml, then docker run upload
    pull_cmd, _ = calls[0]
    assert pull_cmd == ["docker", "pull", DANDI_IMAGE]
    fetch_cmd, _ = calls[1]
    assert fetch_cmd[:2] == ["docker", "run"]
    assert f"{standardized_dir.parent}:{standardized_dir.parent}" in fetch_cmd
    assert "DANDI_CACHE=ignore" in fetch_cmd
    assert fetch_cmd[-10:] == [
        DANDI_IMAGE,
        "dandi",
        "download",
        "-o",
        str(standardized_dir.parent),
        "-e",
        "refresh",
        "--download",
        "dandiset.yaml",
        "dandi://ember-dandi/000002",
    ]
    run_cmd, cwd = calls[2]
    assert run_cmd[:2] == ["docker", "run"]
    assert f"{standardized_dir}:{standardized_dir}" in run_cmd
    assert "-w" in run_cmd and str(standardized_dir) in run_cmd
    assert "DANDI_CACHE=ignore" in run_cmd
    assert run_cmd[-6:] == ["dandi", "upload", "-i", "ember-dandi", "--existing", "refresh"]
    assert cwd is None  # working directory is set inside the container (-w), not on the host


def test_containerize_mounts_paths_and_wraps_cmd(monkeypatch):
    monkeypatch.delenv("EMBER_DANDI_API_KEY", raising=False)
    cmd = dispatch.containerize(
        ["python3", "/repo/labs/x/code/convert.py"],
        image="ghcr.io/example/x-ingest:latest",
        repo_root=Path("/repo"),
        incoming_dir=Path("/incoming/000001"),
        standardized_dir=Path("/standardized/000002"),
        dandi_instance="ember-dandi",
    )
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert "-v" in cmd
    assert "/repo:/repo:ro" in cmd
    assert "/incoming/000001:/incoming/000001" in cmd
    assert "/standardized/000002:/standardized/000002" in cmd
    assert cmd[-3:] == ["ghcr.io/example/x-ingest:latest", "python3", "/repo/labs/x/code/convert.py"]
    assert "EMBER_DANDI_API_KEY" not in cmd  # not set in the environment -> not forwarded


def test_containerize_forwards_dandi_api_key_by_name_only(monkeypatch):
    monkeypatch.setenv("EMBER_DANDI_API_KEY", "super-secret-value")
    cmd = dispatch.containerize(
        ["python3", "/repo/labs/x/code/convert.py"],
        image="ghcr.io/example/x-ingest:latest",
        repo_root=Path("/repo"),
        incoming_dir=Path("/incoming/000001"),
        standardized_dir=Path("/standardized/000002"),
        dandi_instance="ember-dandi",
    )
    assert "EMBER_DANDI_API_KEY" in cmd
    # By name only ("-e EMBER_DANDI_API_KEY", no "=value") -- docker reads
    # the current value from its own environment, so the secret itself
    # never appears in the argv.
    assert not any("super-secret-value" in token for token in cmd)


def test_process_project_runs_conversion_in_container_when_configured(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    calls = []
    record_subprocess(monkeypatch, calls)

    project = make_project(container_image="ghcr.io/example/test-lab-ingest:latest")
    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )

    # docker pull, then the conversion itself wrapped in docker run.
    assert len(calls) == 2
    pull_cmd, _ = calls[0]
    assert pull_cmd == ["docker", "pull", "ghcr.io/example/test-lab-ingest:latest"]
    run_cmd, _ = calls[1]
    assert run_cmd[:2] == ["docker", "run"]
    assert run_cmd[-1] == "--overwrite"  # appended after the templated convert_command
    assert str(standardized_root / "000002") in run_cmd  # convert_command's {standardized_dir} token, unrewritten
    assert "python3" in run_cmd


def test_process_project_auto_appends_metadata_as_flags(tmp_path, monkeypatch):
    """convert_command doesn't need to name a metadata key -- each entry
    becomes its own --<key> <value> flag, appended automatically."""
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    calls = []
    record_subprocess(monkeypatch, calls)

    project = make_project(
        convert_command=["python3", "{repo_root}/labs/test-lab/code/convert.py"],
        metadata={"species": "Mus musculus", "some_key": "some-value"},
    )
    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )
    cmd, _ = calls[0]
    # --overwrite (first-ever run) lands after the auto-appended flags.
    assert cmd[-5:] == ["--species", "Mus musculus", "--some-key", "some-value", "--overwrite"]


def test_process_project_still_supports_explicit_metadata_placeholders(tmp_path, monkeypatch):
    """{key} templating inside convert_command still works too, for a value
    that needs to land somewhere other than a trailing --<key> <value> flag
    (e.g. embedded in a longer token)."""
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    calls = []
    record_subprocess(monkeypatch, calls)

    project = make_project(
        convert_command=["python3", "{repo_root}/labs/test-lab/code/convert-{species}.py"],
        metadata={"species": "mus-musculus"},
    )
    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )
    cmd, _ = calls[0]
    assert str(repo_root / "labs" / "test-lab" / "code" / "convert-mus-musculus.py") in cmd


def make_full_repo(tmp_path: Path) -> Path:
    """A repo_root with a minimal but complete dispatch/ registry, for
    exercising main()'s argument resolution end to end."""
    repo_root = make_repo(tmp_path)
    (repo_root / "dispatch").mkdir()
    (repo_root / "dispatch" / "projects.json").write_text(
        '{"projects": [{'
        '"lab": "test-lab", "incoming_dandiset_id": "000001", "standardized_dandiset_id": "000002", '
        '"script_path": "labs/test-lab/code/convert.py", "convert_command": ["python3"]'
        "}]}"
    )
    (repo_root / "dispatch" / "sessions.json").write_text('{"labs": {"test-lab": {"include": ["raw/*"]}}}')
    return repo_root


def test_main_defaults_incoming_and_standardized_root_to_repo_root_siblings(tmp_path, monkeypatch):
    repo_root = make_full_repo(tmp_path)
    calls = []
    monkeypatch.setattr(dispatch, "process_project", lambda project, **kwargs: calls.append(kwargs))

    assert dispatch.main(["--repo-root", str(repo_root), "--dry-run"]) == 0

    (kwargs,) = calls
    assert kwargs["incoming_root"] == repo_root.parent / "ember-incoming"
    assert kwargs["standardized_root"] == repo_root.parent / "ember-standardized"


def test_main_resolves_relative_repo_root_and_incoming_root_to_absolute(tmp_path, monkeypatch):
    make_full_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(dispatch, "process_project", lambda project, **kwargs: calls.append(kwargs))

    assert dispatch.main(["--repo-root", "repo", "--incoming-root", "somewhere/relative", "--dry-run"]) == 0

    (kwargs,) = calls
    assert kwargs["repo_root"].is_absolute()
    assert kwargs["incoming_root"] == (tmp_path / "somewhere/relative").resolve()
    assert kwargs["incoming_root"].is_absolute()
    assert kwargs["standardized_root"].is_absolute()  # untouched default, still resolved


def test_dry_run_makes_no_filesystem_or_subprocess_changes(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    calls = []
    record_subprocess(monkeypatch, calls)

    project = make_project()
    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        dandi_image=DANDI_IMAGE,
        skip_download=False,
        skip_upload=False,
        dry_run=True,
    )
    assert calls == []
    assert not (standardized_root / "000002").exists()
