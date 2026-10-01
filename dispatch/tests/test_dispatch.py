import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dispatch/

from registry import Project  # noqa: E402
from sessions import SessionSpec  # noqa: E402
from state import IngestState, manifest_filename  # noqa: E402
from tracking import TrackedImage, TrackingDataset  # noqa: E402

import dispatch  # noqa: E402

pytestmark = pytest.mark.ai_generated

SESSION_SPEC = SessionSpec(include=["raw/*"])
DANDI_IMAGE = "ghcr.io/example/dandi-cli:test"


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


def fake_image(self, *, image: str, dry_run: bool) -> TrackedImage:
    name = image.rsplit("/", 1)[-1].split(":")[0]
    tracked = TrackedImage(name=name, path=self.root / "envs" / f"{name}.sif", url=f"docker://{image}@sha256:abc")
    return tracked


@pytest.fixture
def tracking(tmp_path, monkeypatch) -> TrackingDataset:
    """A tracking dataset whose images are already up to date, so a test's
    recorded subprocess calls are only the steps themselves."""
    monkeypatch.setattr(TrackingDataset, "image", fake_image)
    return TrackingDataset(root=tmp_path / "tracking")


def record_calls(monkeypatch) -> list:
    calls = []
    monkeypatch.setattr(dispatch.subprocess, "run", lambda cmd, **kwargs: calls.append((cmd, kwargs)))
    return calls


def step_calls(calls: list) -> list:
    """Drop the `git add` of each record's context.json."""
    steps = [(cmd, kwargs) for cmd, kwargs in calls if cmd[:2] != ["git", "add"]]
    return steps


def make_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    script = repo_root / "labs" / "test-lab" / "code" / "convert.py"
    script.parent.mkdir(parents=True)
    script.write_text("# v1\n")
    return repo_root


def test_process_project_converts_new_sessions_and_records_state(tmp_path, monkeypatch, tracking):
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    calls = record_calls(monkeypatch)

    project = make_project()
    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        tracking=tracking,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )

    # download skipped + upload skipped -> only the conversion ran, recorded
    # with `datalad run` on the host since the project names no image.
    (step,) = step_calls(calls)
    cmd, kwargs = step
    assert cmd[:2] == ["datalad", "run"]
    assert kwargs["cwd"] == tracking.root
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


def test_process_project_skips_when_nothing_new(tmp_path, monkeypatch, tracking):
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

    calls = record_calls(monkeypatch)

    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        tracking=tracking,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )
    assert calls == []  # no conversion, no upload


def test_process_project_nothing_new_skips_upload_even_when_enabled(tmp_path, monkeypatch, tracking):
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

    calls = record_calls(monkeypatch)

    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        tracking=tracking,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=False,
        dry_run=False,
    )
    assert calls == []  # upload enabled, but nothing new -> nothing runs


def test_process_project_forces_overwrite_when_script_changes(tmp_path, monkeypatch, tracking):
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    project = make_project()
    state_dir = standardized_root / "000002"
    state = IngestState(script_sha256="stale-hash")
    state.mark_converted("ses-1", source_path="x", converted_at="t")
    state.save(state_dir)

    calls = record_calls(monkeypatch)

    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        tracking=tracking,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )
    (step,) = step_calls(calls)
    assert "--overwrite" in step[0]

    reloaded = IngestState.load(state_dir)
    assert reloaded.script_sha256 == dispatch.hash_file(project.script_abspath(repo_root))


def test_dandi_credentials_name_the_ember_instances_own_env_var():
    # dandi-cli's own convention (not this script's): the instance name,
    # upper-cased, '-' -> '_', suffixed '_API_KEY'. There is no generic
    # DANDI_API_KEY that would authenticate the ember instance.
    assert dispatch.DANDI_INSTANCE == "ember-dandi"
    assert dispatch.DANDI_API_KEY_ENV_VAR == "EMBER_DANDI_API_KEY"


def test_dandi_download_runs_in_container(tmp_path, monkeypatch, tracking):
    monkeypatch.setenv("EMBER_DANDI_API_KEY", "secret-value")
    incoming_root = tmp_path / "incoming"
    incoming_dir = incoming_root / "000001"

    calls = record_calls(monkeypatch)

    project = make_project()
    dispatch.dandi_download(project, incoming_dir, tracking=tracking, dandi_image=DANDI_IMAGE, dry_run=False)

    (step,) = calls  # a plain download is not recorded in the tracking dataset
    run_cmd, kwargs = step
    sif = str(tracking.root / "envs" / "dandi-cli.sif")
    assert run_cmd == [
        "apptainer",
        "exec",
        "--cleanenv",
        sif,
        "dandi",
        "download",
        "-o",
        str(incoming_root),
        "-e",
        "refresh",
        "dandi://ember-dandi/000001",
    ]
    env = kwargs["env"]
    assert env["APPTAINER_BIND"] == f"{incoming_root}:{incoming_root}"
    assert env["APPTAINERENV_EMBER_DANDI_API_KEY"] == "secret-value"
    assert env["APPTAINERENV_DANDI_CACHE"] == "ignore"  # sidesteps a joblib/fscacher digest-cache race
    assert incoming_root.is_dir()  # created ahead of the bind


def test_dandi_upload_runs_in_container_and_is_recorded(tmp_path, monkeypatch, tracking):
    standardized_dir = tmp_path / "standardized" / "000002"
    standardized_dir.mkdir(parents=True)

    calls = record_calls(monkeypatch)

    project = make_project()
    dispatch.dandi_upload(project, standardized_dir, tracking=tracking, dandi_image=DANDI_IMAGE, dry_run=False)

    fetch, upload = step_calls(calls)
    fetch_cmd, fetch_kwargs = fetch
    assert fetch_cmd[:4] == ["apptainer", "exec", "--cleanenv", str(tracking.root / "envs" / "dandi-cli.sif")]
    assert fetch_cmd[4:] == [
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
    assert fetch_kwargs["env"]["APPTAINER_BIND"] == f"{standardized_dir.parent}:{standardized_dir.parent}"

    upload_cmd, upload_kwargs = upload
    assert upload_cmd[:4] == ["datalad", "containers-run", "--container-name", "dandi-cli"]
    assert upload_cmd[-6:] == ["dandi", "upload", "-i", "ember-dandi", "--existing", "refresh"]
    assert upload_kwargs["cwd"] == tracking.root
    env = upload_kwargs["env"]
    assert env["APPTAINER_BIND"] == f"{standardized_dir}:{standardized_dir}"
    assert env["APPTAINER_PWD"] == str(standardized_dir)
    assert env["APPTAINERENV_DANDI_CACHE"] == "ignore"

    (record_dir,) = (tracking.root / "records" / "test-lab").iterdir()
    assert record_dir.name.endswith("-upload")
    assert env["DUCT_OUTPUT_PREFIX"] == f"{record_dir}/"
    context = json.loads((record_dir / "context.json").read_text())
    assert context["image"] == f"docker://{DANDI_IMAGE}@sha256:abc"


@pytest.mark.parametrize(
    ("upload_validation", "expected_tail"),
    [
        ("require", ["--existing", "refresh"]),
        ("ignore", ["--existing", "refresh", "--validation", "ignore"]),
        ("skip", ["--existing", "refresh", "--validation", "skip"]),
    ],
)
def test_dandi_upload_names_validation_only_when_it_departs_from_the_default(
    tmp_path, monkeypatch, tracking, upload_validation, expected_tail
):
    """The default stays byte-identical, so the flag showing up in a logged
    command is itself the signal that a project uploads unvalidated."""
    standardized_dir = tmp_path / "standardized" / "000002"
    standardized_dir.mkdir(parents=True)

    calls = record_calls(monkeypatch)

    project = make_project(upload_validation=upload_validation)
    dispatch.dandi_upload(project, standardized_dir, tracking=tracking, dandi_image=DANDI_IMAGE, dry_run=False)

    _, (upload_cmd, _) = step_calls(calls)
    assert upload_cmd[-len(expected_tail) :] == expected_tail


@pytest.mark.parametrize("key_set", [True, False])
def test_apptainer_env_forwards_variables_only_through_the_environment(monkeypatch, key_set):
    if key_set:
        monkeypatch.setenv("EMBER_DANDI_API_KEY", "super-secret-value")
    else:
        monkeypatch.delenv("EMBER_DANDI_API_KEY", raising=False)
    env = dispatch.apptainer_env(
        binds={Path("/repo"): ":ro", Path("/incoming/000001"): ""},
        workdir=Path("/repo"),
        forward_env=("EMBER_DANDI_API_KEY",),
    )
    assert env["APPTAINER_BIND"] == "/repo:/repo:ro,/incoming/000001:/incoming/000001"
    assert env["APPTAINER_PWD"] == "/repo"
    assert ("APPTAINERENV_EMBER_DANDI_API_KEY" in env) == key_set


def test_process_project_runs_conversion_in_container_when_configured(tmp_path, monkeypatch, tracking):
    monkeypatch.setenv("EMBER_DANDI_API_KEY", "super-secret-value")
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    calls = record_calls(monkeypatch)

    project = make_project(container_image="ghcr.io/example/test-lab-ingest:latest")
    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        tracking=tracking,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
        task_force_commit="0123abc",
    )

    (step,) = step_calls(calls)
    run_cmd, kwargs = step
    assert run_cmd[:4] == ["datalad", "containers-run", "--container-name", "test-lab-ingest"]
    (record_dir,) = (tracking.root / "records" / "test-lab").iterdir()
    separator = run_cmd.index("--")
    assert run_cmd[separator - 4 : separator] == [
        "--output",
        str(record_dir.relative_to(tracking.root)),
        "--message",
        "[test-lab] Convert 1 session(s)",
    ]
    # The lab command runs under record_run.py, inside the image.
    assert run_cmd[separator + 1 : separator + 3] == ["python3", str(repo_root / "dispatch" / "record_run.py")]
    assert run_cmd[-1] == "--overwrite"  # appended after the templated convert_command
    assert str(standardized_root / "000002") in run_cmd  # convert_command's {standardized_dir} token, unrewritten
    assert not any("super-secret-value" in token for token in run_cmd)

    env = kwargs["env"]
    assert env["APPTAINERENV_EMBER_DANDI_API_KEY"] == "super-secret-value"
    assert f"{repo_root}:{repo_root}:ro" in env["APPTAINER_BIND"].split(",")
    assert f"{record_dir}:{record_dir}" in env["APPTAINER_BIND"].split(",")

    context = json.loads((record_dir / "context.json").read_text())
    assert context["sessions"] == ["ses-1"]
    assert context["task_force_commit"] == "0123abc"
    assert context["image"] == "docker://ghcr.io/example/test-lab-ingest:latest@sha256:abc"


def test_record_escapes_braces_datalad_would_treat_as_placeholders(tmp_path, monkeypatch):
    calls = record_calls(monkeypatch)
    tracking = TrackingDataset(root=tmp_path / "tracking")
    tracking.record(
        cmd=["echo", "{not-a-placeholder}"],
        container="x",
        record_dir=tracking.root / "records" / "lab" / "stamp-convert",
        context={},
        message="m",
        env={},
        dry_run=False,
    )
    (step,) = step_calls(calls)
    assert step[0][-2:] == ["echo", "{{not-a-placeholder}}"]


def test_record_saves_a_failed_run_and_reraises(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["datalad", "containers-run"]:
            raise dispatch.subprocess.CalledProcessError(4, cmd)

    monkeypatch.setattr(dispatch.subprocess, "run", fake_run)
    tracking = TrackingDataset(root=tmp_path / "tracking")
    with pytest.raises(dispatch.subprocess.CalledProcessError):
        tracking.record(
            cmd=["false"],
            container="x",
            record_dir=tracking.root / "records" / "lab" / "stamp-convert",
            context={},
            message="[lab] Convert 1 session(s)",
            env={},
            dry_run=False,
        )
    assert calls[-1] == [
        "datalad",
        "save",
        "--message",
        "[lab] Convert 1 session(s) (failed)",
        str(Path("records") / "lab" / "stamp-convert"),
    ]


def test_process_project_auto_appends_metadata_as_flags(tmp_path, monkeypatch, tracking):
    """convert_command doesn't need to name a metadata key -- each entry
    becomes its own --<key> <value> flag, appended automatically."""
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    calls = record_calls(monkeypatch)

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
        tracking=tracking,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )
    ((cmd, _),) = step_calls(calls)
    # --overwrite (first-ever run) lands after the auto-appended flags.
    assert cmd[-5:] == ["--species", "Mus musculus", "--some-key", "some-value", "--overwrite"]


def test_process_project_still_supports_explicit_metadata_placeholders(tmp_path, monkeypatch, tracking):
    """{key} templating inside convert_command still works too, for a value
    that needs to land somewhere other than a trailing --<key> <value> flag
    (e.g. embedded in a longer token)."""
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    calls = record_calls(monkeypatch)

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
        tracking=tracking,
        dandi_image=DANDI_IMAGE,
        skip_download=True,
        skip_upload=True,
        dry_run=False,
    )
    ((cmd, _),) = step_calls(calls)
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
    assert kwargs["tracking"].root == repo_root.parent / "ember-tracking"


def test_main_refuses_a_real_run_without_a_tracking_dataset(tmp_path, monkeypatch):
    repo_root = make_full_repo(tmp_path)
    calls = []
    monkeypatch.setattr(dispatch, "process_project", lambda project, **kwargs: calls.append(kwargs))

    assert dispatch.main(["--repo-root", str(repo_root), "--tracking", str(tmp_path / "missing")]) == 2
    assert calls == []


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


def test_dry_run_makes_no_filesystem_or_subprocess_changes(tmp_path, monkeypatch, tracking):
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "raw" / "ses-1").mkdir(parents=True)

    calls = record_calls(monkeypatch)

    project = make_project()
    dispatch.process_project(
        project,
        repo_root=repo_root,
        incoming_root=incoming_root,
        standardized_root=standardized_root,
        session_spec=SESSION_SPEC,
        tracking=tracking,
        dandi_image=DANDI_IMAGE,
        skip_download=False,
        skip_upload=False,
        dry_run=True,
    )
    assert calls == []
    assert not (standardized_root / "000002").exists()


def test_process_project_gives_shared_standardized_dir_a_per_project_manifest(tmp_path, monkeypatch, tracking):
    """Two sibling projects (same lab, different `project`) may point at the
    same standardized_dandiset_id -- each nested under its own subdirectory
    -- without clobbering each other's conversion-state manifest."""
    repo_root = make_repo(tmp_path)
    incoming_root = tmp_path / "incoming"
    standardized_root = tmp_path / "standardized"
    (incoming_root / "000001" / "one" / "ses-1").mkdir(parents=True)
    (incoming_root / "000001" / "two" / "ses-2").mkdir(parents=True)

    monkeypatch.setattr(dispatch.subprocess, "run", lambda cmd, **kwargs: None)

    for project_name, session_dir in (("one", "one"), ("two", "two")):
        project = make_project(project=project_name, convert_command=["python3", "convert.py"])
        dispatch.process_project(
            project,
            repo_root=repo_root,
            incoming_root=incoming_root,
            standardized_root=standardized_root,
            session_spec=SessionSpec(include=[f"{session_dir}/*"]),
            tracking=tracking,
            dandi_image=DANDI_IMAGE,
            skip_download=True,
            skip_upload=True,
            dry_run=False,
            shared_standardized=True,
        )

    standardized_dir = standardized_root / "000002"
    manifest_one = IngestState.load(standardized_dir, manifest_name=manifest_filename("test-lab/one", shared=True))
    manifest_two = IngestState.load(standardized_dir, manifest_name=manifest_filename("test-lab/two", shared=True))
    assert manifest_one.converted_sessions.keys() == {"ses-1"}
    assert manifest_two.converted_sessions.keys() == {"ses-2"}


def test_main_marks_standardized_id_shared_only_when_registered_twice(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    (repo_root / "dispatch").mkdir()
    (repo_root / "dispatch" / "projects.json").write_text(
        '{"projects": ['
        '{"lab": "test-lab", "project": "one", "incoming_dandiset_id": "000001", '
        '"standardized_dandiset_id": "000002", "script_path": "labs/test-lab/code/convert.py", '
        '"convert_command": ["python3"]},'
        '{"lab": "test-lab", "project": "two", "incoming_dandiset_id": "000001", '
        '"standardized_dandiset_id": "000002", "script_path": "labs/test-lab/code/convert.py", '
        '"convert_command": ["python3"]}'
        "]}"
    )
    (repo_root / "dispatch" / "sessions.json").write_text(
        '{"labs": {"test-lab/one": {"include": ["one/*"]}, "test-lab/two": {"include": ["two/*"]}}}'
    )
    calls = []
    monkeypatch.setattr(dispatch, "process_project", lambda project, **kwargs: calls.append(kwargs))

    assert dispatch.main(["--repo-root", str(repo_root), "--dry-run"]) == 0

    assert len(calls) == 2
    assert all(kwargs["shared_standardized"] for kwargs in calls)
