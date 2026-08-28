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
     (docker pull + docker run) rather than directly on the runner host --
     the image holds only the lab's runtime environment (e.g. ffmpeg), not
     the code or data, which are bind-mounted in at the same host paths.
  4. ``dandi upload`` the standardized directory (first fetching just its
     dandiset.yaml, since ``dandi upload`` needs one already on disk to
     know which dandiset it's uploading to). Skipped entirely when step 3
     had nothing to do -- upload's no-op check still re-checksums the whole
     local dandiset every pass (DANDI_CACHE=ignore), which is not free.

Every external tool this script drives -- dandi and each lab's own
conversion script -- runs inside a container, not directly on the runner
host: steps 1 and 4 run in --dandi-image (default: this repo's published
dandi-cli image), and step 3 runs in the project's own container_image.
The runner host itself only needs `python3` (to run this orchestrator)
and `docker` (to run everything it drives).

Intended to run unattended on a self-hosted runner via cron
(see data-ingest-runner's .github/workflows/cron_ingest.yml). Every side
effect (download/convert/upload/state write) is skippable with --dry-run,
and any project can be excluded/selected with --only.

--incoming-root/--standardized-root default to 'ember-incoming'/
'ember-standardized' siblings of --repo-root (created as needed) -- no
caller-supplied path required for the common case. Whatever is supplied
or defaulted is always resolved to an absolute path before use, since a
relative one would reach `docker run -v` as a relative host path, which
Docker rejects.

Credentials: this script does not manage DANDI or container-registry auth
itself. `dandi` runs only inside --dandi-image; its credentials come from
EMBER_DANDI_API_KEY in this process's own environment. That name is
dandi-cli's own convention, not this script's: the instance name, upper-
cased, '-' -> '_', suffixed '_API_KEY'. Every docker-run subprocess this
script starts forwards that variable into its container by name only
(`docker run -e EMBER_DANDI_API_KEY`), never as a literal value on the
argv. `docker` itself must already be logged in for any private image
(--dandi-image or a project's container_image) this script names
(`docker login ghcr.io`).
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from registry import DEFAULT_UPLOAD_VALIDATION, Project, load_registry
from sessions import SessionSpec, discover_sessions, load_session_specs
from state import IngestState, hash_file

log = logging.getLogger("dispatch")

DEFAULT_DANDI_IMAGE = "ghcr.io/brain-bbqs/dandi-cli:latest"

# Every dandiset this pipeline touches, incoming and standardized alike,
# lives on the EMBER archive, so the instance is fixed here rather than
# configured per project. Its key env var is named by dandi-cli's own
# convention, spelled out in this module's docstring.
DANDI_INSTANCE = "ember-dandi"
DANDI_API_KEY_ENV_VAR = "EMBER_DANDI_API_KEY"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(cmd: list[str], *, cwd: Path | None = None, dry_run: bool) -> None:
    printable = " ".join(cmd)
    if dry_run:
        log.info("[dry-run] would run: %s%s", printable, f"  (cwd={cwd})" if cwd else "")
        return
    log.info("running: %s%s", printable, f"  (cwd={cwd})" if cwd else "")
    subprocess.run(cmd, cwd=cwd, check=True)


def docker_run_prefix(
    *,
    image: str,
    mounts: dict[Path, str],
    workdir: Path | None = None,
    forward_env: tuple[str, ...] = (),
    literal_env: dict[str, str] | None = None,
) -> list[str]:
    """The 'docker run --rm ...' argv prefix shared by every containerized
    step: bind-mount host paths (mounts maps host path -> a docker -v mode
    suffix, e.g. "" for read-write or ":ro"), set a working directory,
    forward named environment variables by name only -- "-e NAME" with no
    "=value" makes docker read the current value from this process's own
    environment, so a secret never appears as a literal on the argv, where
    `ps` or process-listing tools could see it -- and set literal_env
    entries with an explicit "=value" (for non-secret config, not
    credentials)."""
    prefix = ["docker", "run", "--rm"]
    for host_path, mode in mounts.items():
        prefix += ["-v", f"{host_path}:{host_path}{mode}"]
    if workdir is not None:
        prefix += ["-w", str(workdir)]
    for var in forward_env:
        if var in os.environ:
            prefix += ["-e", var]
    for key, value in (literal_env or {}).items():
        prefix += ["-e", f"{key}={value}"]
    prefix.append(image)
    return prefix


# dandi-cli caches file checksums on disk (fscacher, keyed by DANDI_CACHE)
# to avoid rehashing unchanged files across runs -- a benefit this script
# never gets anyway, since every dandi container is `--rm` and starts with
# an empty cache dir every time. Worse, a checksum computed in a fresh cache
# dir has a known joblib race (JobLibCollisionWarning between two identically
# named get_digest functions) that can fail an upload outright ("failed to
# compute digest: ... func_code.py"). Disabling it costs nothing here and
# sidesteps that race, so every dandi invocation sets DANDI_CACHE=ignore.
DANDI_CACHE_ENV = {"DANDI_CACHE": "ignore"}


def dandi_download(project: Project, incoming_dir: Path, *, dandi_image: str, dry_run: bool) -> None:
    url = f"dandi://{DANDI_INSTANCE}/{project.incoming_dandiset_id}"
    if not dry_run:
        incoming_dir.parent.mkdir(parents=True, exist_ok=True)
    run(["docker", "pull", dandi_image], dry_run=dry_run)
    cmd = docker_run_prefix(
        image=dandi_image,
        mounts={incoming_dir.parent: ""},
        forward_env=(DANDI_API_KEY_ENV_VAR,),
        literal_env=DANDI_CACHE_ENV,
    ) + ["dandi", "download", "-o", str(incoming_dir.parent), "-e", "refresh", url]
    run(cmd, dry_run=dry_run)


def dandi_upload(project: Project, standardized_dir: Path, *, dandi_image: str, dry_run: bool) -> None:
    if not dry_run and not standardized_dir.is_dir():
        log.info("[%s] no standardized output yet at %s, skipping upload", project.key, standardized_dir)
        return
    run(["docker", "pull", dandi_image], dry_run=dry_run)
    forward_env = (DANDI_API_KEY_ENV_VAR,)
    # `dandi upload` identifies its target dandiset from a dandiset.yaml it
    # walks up from cwd to find -- one only ever lands here via a prior
    # `dandi download` of standardized_dandiset_id, which never happens on
    # its own when standardized_dandiset_id differs from incoming_dandiset_id
    # (the only one dispatch downloads). Fetch just that file -- not the
    # whole dandiset -- so upload works before any such download has.
    url = f"dandi://{DANDI_INSTANCE}/{project.standardized_dandiset_id}"
    fetch_dandiset_yaml_cmd = docker_run_prefix(
        image=dandi_image,
        mounts={standardized_dir.parent: ""},
        forward_env=forward_env,
        literal_env=DANDI_CACHE_ENV,
    ) + ["dandi", "download", "-o", str(standardized_dir.parent), "-e", "refresh", "--download", "dandiset.yaml", url]
    run(fetch_dandiset_yaml_cmd, dry_run=dry_run)
    cmd = docker_run_prefix(
        image=dandi_image,
        mounts={standardized_dir: ""},
        workdir=standardized_dir,
        forward_env=forward_env,
        literal_env=DANDI_CACHE_ENV,
    ) + ["dandi", "upload", "-i", DANDI_INSTANCE, "--existing", "refresh"]
    # Only named when the project departs from dandi's own default, so the
    # flag's presence in the logged command is the signal that this project
    # uploads without validation gating it.
    if project.upload_validation != DEFAULT_UPLOAD_VALIDATION:
        cmd += ["--validation", project.upload_validation]
    run(cmd, dry_run=dry_run)


def containerize(
    cmd: list[str],
    *,
    image: str,
    repo_root: Path,
    incoming_dir: Path,
    standardized_dir: Path,
) -> list[str]:
    """Wrap cmd to run inside a lab's published container image (portable
    Python env only -- ffmpeg, etc. -- not the code or data, which are
    mounted in at run time). Host paths are mounted at identical paths
    inside the container, so cmd's own {repo_root}/{incoming_dir}/
    {standardized_dir}-based tokens (already resolved, absolute) need no
    rewriting. The DANDI API key env var is forwarded too, in case the
    conversion script itself needs to talk to DANDI."""
    prefix = docker_run_prefix(
        image=image,
        mounts={repo_root: ":ro", incoming_dir: "", standardized_dir: ""},
        workdir=repo_root,
        forward_env=(DANDI_API_KEY_ENV_VAR,),
    )
    return prefix + cmd


def convert(
    project: Project,
    *,
    repo_root: Path,
    incoming_dir: Path,
    standardized_dir: Path,
    force_overwrite: bool,
    dry_run: bool,
) -> None:
    cmd = [
        token.format(
            repo_root=repo_root,
            incoming_dir=incoming_dir,
            standardized_dir=standardized_dir,
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
    if project.container_image:
        # Refresh a floating tag (e.g. :latest) rather than trusting
        # whatever's already cached locally on the runner.
        run(["docker", "pull", project.container_image], dry_run=dry_run)
        cmd = containerize(
            cmd,
            image=project.container_image,
            repo_root=repo_root,
            incoming_dir=incoming_dir,
            standardized_dir=standardized_dir,
        )
    run(cmd, dry_run=dry_run)


def process_project(
    project: Project,
    *,
    repo_root: Path,
    incoming_root: Path,
    standardized_root: Path,
    session_spec: SessionSpec,
    dandi_image: str,
    skip_download: bool,
    skip_upload: bool,
    dry_run: bool,
) -> None:
    incoming_dir = incoming_root / project.incoming_dandiset_id
    standardized_dir = standardized_root / project.standardized_dandiset_id
    log.info("=== %s: %s -> %s ===", project.key, project.incoming_dandiset_id, project.standardized_dandiset_id)

    if not skip_download:
        dandi_download(project, incoming_dir, dandi_image=dandi_image, dry_run=dry_run)
    else:
        log.info("[%s] --skip-download set, using existing local copy", project.key)

    state = IngestState.load(standardized_dir)

    script_path = project.script_abspath(repo_root)
    current_script_hash = hash_file(script_path) if script_path.is_file() else None
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
            "[%s] conversion script changed (%s -> %s); reprocessing all %d discovered session(s)",
            project.key,
            state.script_sha256,
            current_script_hash,
            len(discovered),
        )
    else:
        log.info("[%s] %d new session(s): %s", project.key, len(new_sessions), ", ".join(new_sessions))

    convert(
        project,
        repo_root=repo_root,
        incoming_dir=incoming_dir,
        standardized_dir=standardized_dir,
        force_overwrite=script_changed,
        dry_run=dry_run,
    )

    converted_at = now_iso()
    for session_id in discovered if script_changed else new_sessions:
        state.mark_converted(
            session_id,
            source_path=str(session_paths_by_id[session_id]),
            converted_at=converted_at,
        )
    if current_script_hash is not None:
        state.script_sha256 = current_script_hash
    state.last_run_at = converted_at
    touched = discovered if script_changed else new_sessions
    if not dry_run:
        state.save(standardized_dir)
    else:
        log.info("[%s] [dry-run] would write state for %d session(s)", project.key, len(touched))

    if not skip_upload:
        dandi_upload(project, standardized_dir, dandi_image=dandi_image, dry_run=dry_run)


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
    # --standardized-root/--repo-root values would otherwise reach `docker
    # run -v` as relative host paths, which Docker rejects outright.
    args.repo_root = args.repo_root.resolve()
    args.incoming_root = (args.incoming_root or args.repo_root.parent / "ember-incoming").resolve()
    args.standardized_root = (args.standardized_root or args.repo_root.parent / "ember-standardized").resolve()
    log.info("repo_root=%s", args.repo_root)
    log.info("incoming_root=%s", args.incoming_root)
    log.info("standardized_root=%s", args.standardized_root)

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
                dandi_image=args.dandi_image,
                skip_download=args.skip_download,
                skip_upload=args.skip_upload,
                dry_run=args.dry_run,
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
