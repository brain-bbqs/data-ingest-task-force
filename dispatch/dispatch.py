#!/usr/bin/env python3
"""Cron entrypoint that drives one pass of the ingest pipeline for every
registered project (see projects.json):

  1. ``dandi download`` the incoming dandiset into ``<incoming-root>/<id>``.
  2. Diff its sessions (dispatch/sessions.json's spec for the project)
     against the project's manifest to find sessions that haven't been
     converted yet with the current script.
  3. If there's new work (or the conversion script itself changed), run the
     lab's conversion command, writing into ``<standardized-root>/<id>``.
     If the project names a container_image, the command runs inside it
     (via Apptainer) rather than directly on the runner host -- the image
     holds only the lab's runtime environment (e.g. ffmpeg), not the code
     or data, which are bind-mounted in at the same host paths.
  4. ``dandi upload`` the standardized directory (first fetching just its
     dandiset.yaml, since ``dandi upload`` needs one already on disk to
     know which dandiset it's uploading to). Skipped entirely when step 3
     had nothing to do -- upload's no-op check still re-checksums the whole
     local dandiset every pass (DANDI_CACHE=ignore), which is not free.

Every external tool this script drives -- dandi and each lab's own
conversion script -- runs inside an Apptainer container, not directly on
the runner host: steps 1 and 4 in --dandi-image (default: this repo's
published dandi-cli image), and step 3 in the project's own
container_image. Images are pulled from their registries as .sif files into
the tracking dataset (--tracking, see tracking.py), pinned to the digest
their tag points at, and steps 3 and 4 run through ``datalad
containers-run`` under con-duct there, so each conversion and upload
becomes one commit holding its logs, resource usage, and output manifest.
The runner host itself needs `python3` (to run this orchestrator),
`apptainer`, `git-annex`, `datalad`, `datalad-container`, and `con-duct`.

Intended to run unattended on a self-hosted runner via cron
(see data-ingest-runner's .github/workflows/scheduled_ingest.yml). Every
side effect (download/convert/upload/state write/tracking commit) is
skippable with --dry-run, and any project can be excluded/selected with
--only.

--incoming-root/--standardized-root/--tracking default to 'ember-incoming'/
'ember-standardized'/'ember-tracking' siblings of --repo-root -- no
caller-supplied path required for the common case. Whatever is supplied or
defaulted is always resolved to an absolute path before use, since a
relative one would reach APPTAINER_BIND as a relative host path.

Credentials: this script does not manage DANDI or container-registry auth
itself. `dandi` runs only inside --dandi-image; its credentials come from
EMBER_DANDI_API_KEY in this process's own environment. That name is
dandi-cli's own convention, not this script's: the instance name, upper-
cased, '-' -> '_', suffixed '_API_KEY'. Every container this script starts
receives that variable through the environment (APPTAINERENV_<name>, which
survives --cleanenv), never as a literal value on an argv, so it never
lands in a logged command or a tracking-dataset run record. Images are
resolved anonymously, so only public images are supported for now.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from commands import run
from registry import DEFAULT_UPLOAD_VALIDATION, Project, load_registry
from sessions import SessionSpec, discover_sessions, load_session_specs
from state import IngestState, hash_file, manifest_filename
from tracking import TrackingDataset, TrackingError

log = logging.getLogger("dispatch")

DEFAULT_DANDI_IMAGE = "ghcr.io/brain-bbqs/dandi-cli:latest"

# Every dandiset this pipeline touches, incoming and standardized alike,
# lives on the EMBER archive, so the instance is fixed here rather than
# configured per project. Its key env var is named by dandi-cli's own
# convention, spelled out in this module's docstring.
DANDI_INSTANCE = "ember-dandi"
DANDI_API_KEY_ENV_VAR = "EMBER_DANDI_API_KEY"

RECORD_RUN_SCRIPT = Path("dispatch") / "record_run.py"
# Where a convert_command's {results} placeholder points, inside the run's record.
RESULTS_FILENAME = "results.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def apptainer_env(
    *,
    binds: dict[Path, str],
    workdir: Path | None = None,
    forward_env: tuple[str, ...] = (),
    literal_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """The environment for an Apptainer call, carrying everything that
    differs between steps so the command line itself stays the same: bind
    host paths at identical container paths (binds maps host path -> "" for
    read-write or ":ro"), set a working directory, and pass variables
    through --cleanenv. A forwarded variable's value only ever travels in
    the environment, never on an argv, where `ps`, a log line, or a DataLad
    run record could capture it."""
    env = dict(os.environ)
    env["APPTAINER_BIND"] = ",".join(f"{path}:{path}{mode}" for path, mode in binds.items())
    if workdir is not None:
        env["APPTAINER_PWD"] = str(workdir)
    for var in forward_env:
        if var in os.environ:
            env[f"APPTAINERENV_{var}"] = os.environ[var]
    for key, value in (literal_env or {}).items():
        env[f"APPTAINERENV_{key}"] = value
    return env


def git_head(repo_root: Path, /) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return None
    commit = result.stdout.strip() if result.returncode == 0 else None
    return commit


# dandi-cli caches file checksums on disk (fscacher, keyed by DANDI_CACHE)
# to avoid rehashing unchanged files across runs -- a benefit this script
# never gets anyway, since every dandi container starts from a fresh
# environment. Worse, a checksum computed in a fresh cache dir has a known
# joblib race (JobLibCollisionWarning between two identically named
# get_digest functions) that can fail an upload outright ("failed to
# compute digest: ... func_code.py"). Disabling it costs nothing here and
# sidesteps that race, so every dandi invocation sets DANDI_CACHE=ignore.
DANDI_CACHE_ENV = {"DANDI_CACHE": "ignore"}


def dandi_download(
    project: Project, incoming_dir: Path, *, tracking: TrackingDataset, dandi_image: str, dry_run: bool
) -> None:
    url = f"dandi://{DANDI_INSTANCE}/{project.incoming_dandiset_id}"
    if not dry_run:
        incoming_dir.parent.mkdir(parents=True, exist_ok=True)
    image = tracking.image(image=dandi_image, dry_run=dry_run)
    env = apptainer_env(
        binds={incoming_dir.parent: ""},
        forward_env=(DANDI_API_KEY_ENV_VAR,),
        literal_env=DANDI_CACHE_ENV,
    )
    cmd = ["apptainer", "exec", "--cleanenv", str(image.path)]
    cmd += ["dandi", "download", "-o", str(incoming_dir.parent), "-e", "refresh", url]
    run(cmd, env=env, dry_run=dry_run)


def dandi_upload(
    project: Project, standardized_dir: Path, *, tracking: TrackingDataset, dandi_image: str, dry_run: bool
) -> None:
    if not dry_run and not standardized_dir.is_dir():
        log.info("[%s] no standardized output yet at %s, skipping upload", project.key, standardized_dir)
        return
    image = tracking.image(image=dandi_image, dry_run=dry_run)
    forward_env = (DANDI_API_KEY_ENV_VAR,)
    # `dandi upload` identifies its target dandiset from a dandiset.yaml it
    # walks up from cwd to find -- one only ever lands here via a prior
    # `dandi download` of standardized_dandiset_id, which never happens on
    # its own when standardized_dandiset_id differs from incoming_dandiset_id
    # (the only one dispatch downloads). Fetch just that file -- not the
    # whole dandiset -- so upload works before any such download has.
    url = f"dandi://{DANDI_INSTANCE}/{project.standardized_dandiset_id}"
    fetch_env = apptainer_env(
        binds={standardized_dir.parent: ""},
        forward_env=forward_env,
        literal_env=DANDI_CACHE_ENV,
    )
    fetch_dandiset_yaml_cmd = ["apptainer", "exec", "--cleanenv", str(image.path)]
    fetch_dandiset_yaml_cmd += ["dandi", "download", "-o", str(standardized_dir.parent), "-e", "refresh"]
    fetch_dandiset_yaml_cmd += ["--download", "dandiset.yaml", url]
    run(fetch_dandiset_yaml_cmd, env=fetch_env, dry_run=dry_run)

    cmd = ["dandi", "upload", "-i", DANDI_INSTANCE, "--existing", "refresh"]
    # Only named when the project departs from dandi's own default, so the
    # flag's presence in the logged command is the signal that this project
    # uploads without validation gating it.
    if project.upload_validation != DEFAULT_UPLOAD_VALIDATION:
        cmd += ["--validation", project.upload_validation]
    upload_env = apptainer_env(
        binds={standardized_dir: ""},
        workdir=standardized_dir,
        forward_env=forward_env,
        literal_env=DANDI_CACHE_ENV,
    )
    tracking.record(
        cmd=cmd,
        container=image.name,
        record_dir=tracking.new_record_dir(project_key=project.key, step="upload"),
        context={
            "project": project.key,
            "step": "upload",
            "standardized_dandiset_id": project.standardized_dandiset_id,
            "image": image.url,
        },
        message=f"[{project.key}] Upload {standardized_dir.name} to {DANDI_INSTANCE}",
        env=upload_env,
        dry_run=dry_run,
    )


def convert(
    project: Project,
    *,
    repo_root: Path,
    incoming_dir: Path,
    standardized_dir: Path,
    tracking: TrackingDataset,
    sessions: list[str],
    script_sha256: str | None,
    task_force_commit: str | None,
    force_overwrite: bool,
    dry_run: bool,
) -> dict[str, dict[str, str]]:
    """Run the conversion. Returns the sessions it left unconverted, as
    ``{"pending": {id: reason}, "failed": {id: reason}}``.

    A command that writes the ``{results}`` file may fail for some sessions
    without failing the step: those sessions are returned rather than
    raised, so the rest are still recorded and uploaded.
    """
    record_dir = tracking.new_record_dir(project_key=project.key, step="convert")
    results_path = record_dir / RESULTS_FILENAME
    cmd = [
        token.format(
            repo_root=repo_root,
            incoming_dir=incoming_dir,
            standardized_dir=standardized_dir,
            results=results_path,
            **project.metadata,
        )
        for token in project.convert_command
    ]
    # Every metadata entry becomes a --<key> <value> flag automatically, so
    # convert_command doesn't need to name each one -- a project only has to
    # declare e.g. {"species": "Ovis aries"} once, in metadata, not also
    # spell out "--species" in its own command template.
    for key, value in project.metadata.items():
        cmd += [f"--{key.replace('_', '-')}", value]
    if force_overwrite and project.overwrite_flag:
        cmd.append(project.overwrite_flag)
    if not dry_run:
        standardized_dir.mkdir(parents=True, exist_ok=True)

    # Runs under the image's own python3 when containerized, so the manifest
    # of what the conversion wrote is produced inside the recorded run.
    recorded_cmd = [
        "python3",
        str(repo_root / RECORD_RUN_SCRIPT),
        "--cwd",
        str(repo_root),
        "--root",
        str(standardized_dir),
        "--manifest",
        str(record_dir / "manifest.json"),
        "--",
    ] + cmd
    context = {
        "project": project.key,
        "step": "convert",
        "incoming_dandiset_id": project.incoming_dandiset_id,
        "standardized_dandiset_id": project.standardized_dandiset_id,
        "task_force_commit": task_force_commit,
        "script_path": project.script_path,
        "script_sha256": script_sha256,
        "force_overwrite": force_overwrite,
        "sessions": sessions,
    }
    message = f"[{project.key}] Convert {len(sessions)} session(s)"
    if project.container_image:
        image = tracking.image(image=project.container_image, dry_run=dry_run)
        context["image"] = image.url
        # The DANDI API key is forwarded too, in case the conversion script
        # itself needs to talk to DANDI.
        env = apptainer_env(
            binds={repo_root: ":ro", incoming_dir: "", standardized_dir: "", record_dir: ""},
            forward_env=(DANDI_API_KEY_ENV_VAR,),
        )
        container = image.name
    else:
        env = dict(os.environ)
        container = None
    try:
        tracking.record(
            cmd=recorded_cmd,
            container=container,
            record_dir=record_dir,
            context=context,
            message=message,
            env=env,
            dry_run=dry_run,
        )
    except subprocess.CalledProcessError:
        unconverted = read_results(results_path, sessions=sessions)
        if unconverted is None:
            raise
        return unconverted
    unconverted = read_results(results_path, sessions=sessions) or {"pending": {}, "failed": {}}
    return unconverted


def read_results(path: Path, /, *, sessions: list[str]) -> dict[str, dict[str, str]] | None:
    """The unconverted sessions a conversion listed in its results file, or
    None when it wrote none (or one naming sessions it wasn't given), in
    which case a failed step stays a failure of the whole project."""
    if not path.is_file():
        return None
    payload = json.loads(path.read_text())
    unconverted = {kind: dict(payload.get(kind) or {}) for kind in ("pending", "failed")}
    listed = set(unconverted["pending"]) | set(unconverted["failed"])
    if not listed or not listed <= set(sessions):
        return None
    return unconverted


class ConversionIncomplete(RuntimeError):
    """Some sessions failed to convert. The rest were still recorded and uploaded."""


def conversion_inputs(project: Project, /, *, repo_root: Path) -> list[Path]:
    """The conversion script plus every repository file its convert_command
    names, such as a batch driver or a config. A change to any of them
    changes what the conversion writes."""
    named = []
    for token in project.convert_command:
        if not token.startswith("{repo_root}/"):
            continue
        path = Path(token.replace("{repo_root}", str(repo_root), 1))
        if path.is_file():
            named.append(path)
    script = project.script_abspath(repo_root)
    inputs = [script] + sorted({path for path in named if path != script})
    return inputs


def conversion_hash(project: Project, /, *, repo_root: Path) -> str:
    """sha256 identifying the conversion's code and config. With only the
    script to hash it is the script's own hash, so projects whose command
    names no other file keep the hash their manifests already record."""
    inputs = conversion_inputs(project, repo_root=repo_root)
    if len(inputs) == 1:
        return hash_file(inputs[0])
    digest = hashlib.sha256()
    for path in inputs:
        digest.update(f"{path.relative_to(repo_root)}\0{hash_file(path)}\n".encode())
    combined = digest.hexdigest()
    return combined


def process_project(
    project: Project,
    *,
    repo_root: Path,
    incoming_root: Path,
    standardized_root: Path,
    session_spec: SessionSpec,
    tracking: TrackingDataset,
    dandi_image: str,
    skip_download: bool,
    skip_upload: bool,
    dry_run: bool,
    shared_standardized: bool = False,
    task_force_commit: str | None = None,
) -> None:
    incoming_dir = incoming_root / project.incoming_dandiset_id
    standardized_dir = standardized_root / project.standardized_dandiset_id
    log.info("=== %s: %s -> %s ===", project.key, project.incoming_dandiset_id, project.standardized_dandiset_id)

    if not skip_download:
        dandi_download(project, incoming_dir, tracking=tracking, dandi_image=dandi_image, dry_run=dry_run)
    else:
        log.info("[%s] --skip-download set, using existing local copy", project.key)

    manifest_name = manifest_filename(project.key, shared=shared_standardized)
    state = IngestState.load(standardized_dir, manifest_name=manifest_name)

    script_path = project.script_abspath(repo_root)
    current_script_hash = conversion_hash(project, repo_root=repo_root) if script_path.is_file() else None
    if current_script_hash is None:
        log.warning("[%s] conversion script not found at %s, cannot hash it", project.key, script_path)
    script_changed = current_script_hash is not None and current_script_hash != state.script_sha256

    discovered_paths = [] if dry_run and not incoming_dir.is_dir() else discover_sessions(incoming_dir, session_spec)
    session_paths_by_id = {p.name: p for p in discovered_paths}
    discovered = list(session_paths_by_id)
    new_sessions = state.new_sessions(discovered)

    if not new_sessions and not script_changed:
        # No upload either: everything already recorded in the manifest was
        # uploaded by the run that converted it, and re-checking costs a full
        # local re-checksum of the dandiset (DANDI_CACHE=ignore) every pass.
        log.info(
            "[%s] nothing new (%d known sessions, script unchanged), skipping upload", project.key, len(discovered)
        )
        return

    if script_changed:
        log.info(
            "[%s] conversion script or config changed (%s -> %s); reprocessing all %d discovered session(s)",
            project.key,
            state.script_sha256,
            current_script_hash,
            len(discovered),
        )
    else:
        log.info("[%s] %d new session(s): %s", project.key, len(new_sessions), ", ".join(new_sessions))

    touched = discovered if script_changed else new_sessions
    unconverted = convert(
        project,
        repo_root=repo_root,
        incoming_dir=incoming_dir,
        standardized_dir=standardized_dir,
        tracking=tracking,
        sessions=touched,
        script_sha256=current_script_hash,
        task_force_commit=task_force_commit,
        force_overwrite=script_changed,
        dry_run=dry_run,
    )

    # Unconverted sessions stay out of the state, so the next run retries them.
    skipped = set(unconverted["pending"]) | set(unconverted["failed"])
    converted_at = now_iso()
    for session_id in (session for session in touched if session not in skipped):
        state.mark_converted(
            session_id,
            source_path=str(session_paths_by_id[session_id]),
            converted_at=converted_at,
        )
    if current_script_hash is not None:
        state.script_sha256 = current_script_hash
    state.last_run_at = converted_at
    if not dry_run:
        state.save(standardized_dir, manifest_name=manifest_name)
    else:
        log.info("[%s] [dry-run] would write state for %d session(s)", project.key, len(touched))

    if skip_upload:
        pass
    elif skipped >= set(touched):
        # Only retried sessions still waiting on inputs: nothing new to
        # upload, and the upload's no-op check re-checksums the whole dandiset.
        log.info("[%s] no session converted this run, skipping upload", project.key)
    else:
        dandi_upload(project, standardized_dir, tracking=tracking, dandi_image=dandi_image, dry_run=dry_run)

    if unconverted["pending"]:
        # Waiting on inputs, not broken: a warning, so the run still passes.
        summary = f"{len(unconverted['pending'])} session(s) waiting on missing inputs, retried next run"
        log.warning("[%s] %s:", project.key, summary)
        for session_id, reason in sorted(unconverted["pending"].items()):
            log.warning("[%s]   %s: %s", project.key, session_id, reason)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title={project.key}::{summary}: {', '.join(sorted(unconverted['pending']))}", flush=True)
    if unconverted["failed"]:
        details = "; ".join(f"{session_id}: {reason}" for session_id, reason in sorted(unconverted["failed"].items()))
        raise ConversionIncomplete(f"{len(unconverted['failed'])} session(s) failed to convert: {details}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    default_repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=default_repo_root,
        help="Checkout of data-ingest-task-force (default: repo containing this script).",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Path to projects.json (default: <repo-root>/dispatch/projects.json).",
    )
    parser.add_argument(
        "--sessions",
        type=Path,
        default=None,
        help="Path to sessions.json (default: <repo-root>/dispatch/sessions.json).",
    )
    parser.add_argument(
        "--incoming-root",
        type=Path,
        default=None,
        help="Top-level 'ember-incoming' folder of local dandiset copies "
        "(default: an 'ember-incoming' sibling of --repo-root, created as needed).",
    )
    parser.add_argument(
        "--standardized-root",
        type=Path,
        default=None,
        help="Top-level 'ember-standardized' folder for converted output "
        "(default: an 'ember-standardized' sibling of --repo-root, created as needed).",
    )
    parser.add_argument(
        "--tracking",
        type=Path,
        default=None,
        help="Local clone of the data-ingest-runner-tracking DataLad dataset, which holds the container images "
        "and a record of every conversion and upload (default: an 'ember-tracking' sibling of --repo-root).",
    )
    parser.add_argument(
        "--dandi-image",
        default=DEFAULT_DANDI_IMAGE,
        help="Container image the dandi CLI (download/upload) runs inside.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help="Restrict to this project key (repeatable): a lab name, or '<lab>/<project>' for a lab "
        "running several projects. Default: all registered projects.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Don't run 'dandi download'; use whatever is already in --incoming-root.",
    )
    parser.add_argument("--skip-upload", action="store_true", help="Don't run 'dandi upload' after conversion.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log every action without downloading, converting, uploading, or writing state.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(message)s")

    # Resolve to absolute paths unconditionally: relative --incoming-root/
    # --standardized-root/--repo-root values would otherwise reach
    # APPTAINER_BIND as relative host paths.
    args.repo_root = args.repo_root.resolve()
    args.incoming_root = (args.incoming_root or args.repo_root.parent / "ember-incoming").resolve()
    args.standardized_root = (args.standardized_root or args.repo_root.parent / "ember-standardized").resolve()
    args.tracking = (args.tracking or args.repo_root.parent / "ember-tracking").resolve()
    log.info("repo_root=%s", args.repo_root)
    log.info("incoming_root=%s", args.incoming_root)
    log.info("standardized_root=%s", args.standardized_root)
    log.info("tracking=%s", args.tracking)

    tracking = TrackingDataset(root=args.tracking)
    if not args.dry_run:
        try:
            tracking.check()
        except TrackingError as error:
            log.error("%s", error)
            return 2
    commit = git_head(args.repo_root)

    registry_path = args.registry or (args.repo_root / "dispatch" / "projects.json")
    sessions_path = args.sessions or (args.repo_root / "dispatch" / "sessions.json")
    projects = load_registry(registry_path)
    session_specs = load_session_specs(sessions_path)
    if args.only:
        wanted = set(args.only)
        projects = [p for p in projects if p.key in wanted]
        missing = wanted - {p.key for p in projects}
        if missing:
            log.error("--only named unknown project(s): %s", ", ".join(sorted(missing)))
            return 2

    # Whether a project's standardized_dandiset_id is registered more than
    # once decides its manifest filename (state.manifest_filename) -- only
    # visible here, with the full registry in hand.
    standardized_id_counts = Counter(p.standardized_dandiset_id for p in projects)

    failures = []
    for project in projects:
        spec = session_specs.get(project.key)
        if spec is None:
            log.error("[%s] no entry in %s; skipping", project.key, sessions_path)
            failures.append(project.key)
            continue
        try:
            process_project(
                project,
                repo_root=args.repo_root,
                incoming_root=args.incoming_root,
                standardized_root=args.standardized_root,
                session_spec=spec,
                tracking=tracking,
                dandi_image=args.dandi_image,
                skip_download=args.skip_download,
                skip_upload=args.skip_upload,
                dry_run=args.dry_run,
                shared_standardized=standardized_id_counts[project.standardized_dandiset_id] > 1,
                task_force_commit=commit,
            )
        except Exception:
            log.exception("[%s] failed; continuing with remaining projects", project.key)
            failures.append(project.key)

    if failures:
        log.error("failed project(s): %s", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
