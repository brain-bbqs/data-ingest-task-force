#!/usr/bin/env python3
"""Cron entrypoint that drives one pass of the ingest pipeline for every
registered project (see projects.yaml):

  1. ``dandi download`` the incoming dandiset into ``<incoming-root>/<id>``.
  2. Diff its sessions (``session_glob``) against the project's manifest to
     find sessions that haven't been converted yet with the current script.
  3. If there's new work (or the conversion script itself changed), run the
     lab's conversion command, writing into ``<standardized-root>/<id>``.
  4. ``dandi upload`` the standardized directory.

Intended to run unattended on a self-hosted runner via cron
(see data-ingest-runner's .github/workflows/cron_ingest.yml). Every side
effect (download/convert/upload/state write) is skippable with --dry-run,
and any project can be excluded/selected with --only.

Credentials: this script does not manage DANDI auth itself. It shells out to
the `dandi` CLI, which must already be configured on the runner for the
instance(s) named in projects.yaml (`dandi login -i <instance>`, or the
API-key env var dandi-cli itself supports) before this runs.
"""

from __future__ import annotations

import argparse
import glob
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from registry import Project, load_registry
from state import IngestState, hash_file

log = logging.getLogger("dispatch")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(cmd: list[str], *, cwd: Path | None = None, dry_run: bool) -> None:
    printable = " ".join(cmd)
    if dry_run:
        log.info("[dry-run] would run: %s%s", printable, f"  (cwd={cwd})" if cwd else "")
        return
    log.info("running: %s%s", printable, f"  (cwd={cwd})" if cwd else "")
    subprocess.run(cmd, cwd=cwd, check=True)


def dandi_download(project: Project, incoming_dir: Path, *, dry_run: bool) -> None:
    url = f"dandi://{project.dandi_instance}/{project.incoming_dandiset_id}"
    if not dry_run:
        incoming_dir.parent.mkdir(parents=True, exist_ok=True)
    run(
        ["dandi", "download", "-o", str(incoming_dir.parent), "-e", "refresh", url],
        dry_run=dry_run,
    )


def dandi_upload(project: Project, standardized_dir: Path, *, dry_run: bool) -> None:
    if not dry_run and not standardized_dir.is_dir():
        log.info("[%s] no standardized output yet at %s, skipping upload", project.lab, standardized_dir)
        return
    run(
        ["dandi", "upload", "-i", project.dandi_instance, "--existing", "refresh"],
        cwd=standardized_dir,
        dry_run=dry_run,
    )


def discover_sessions(incoming_dir: Path, session_glob: str) -> list[str]:
    """Session ids = basenames of session_glob's directory matches (a session
    is a folder; stray files alongside them, e.g. notes.txt, are ignored)."""
    matches = sorted(glob.glob(str(incoming_dir / session_glob)))
    return [Path(m).name for m in matches if Path(m).is_dir()]


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
        )
        for token in project.convert_command
    ]
    if force_overwrite and project.overwrite_flag:
        cmd.append(project.overwrite_flag)
    if not dry_run:
        standardized_dir.mkdir(parents=True, exist_ok=True)
    run(cmd, dry_run=dry_run)


def process_project(
    project: Project,
    *,
    repo_root: Path,
    incoming_root: Path,
    standardized_root: Path,
    skip_download: bool,
    skip_upload: bool,
    dry_run: bool,
) -> None:
    incoming_dir = incoming_root / project.incoming_dandiset_id
    standardized_dir = standardized_root / project.standardized_dandiset_id
    log.info("=== %s: %s -> %s ===", project.lab, project.incoming_dandiset_id, project.standardized_dandiset_id)

    if not skip_download:
        dandi_download(project, incoming_dir, dry_run=dry_run)
    else:
        log.info("[%s] --skip-download set, using existing local copy", project.lab)

    state = IngestState.load(standardized_dir)

    script_path = project.script_abspath(repo_root)
    current_script_hash = hash_file(script_path) if script_path.is_file() else None
    if current_script_hash is None:
        log.warning("[%s] conversion script not found at %s, cannot hash it", project.lab, script_path)
    script_changed = current_script_hash is not None and current_script_hash != state.script_sha256

    discovered = [] if dry_run and not incoming_dir.is_dir() else discover_sessions(incoming_dir, project.session_glob)
    new_sessions = state.new_sessions(discovered)

    if not new_sessions and not script_changed:
        log.info("[%s] nothing new (%d known sessions, script unchanged)", project.lab, len(discovered))
        if not skip_upload:
            dandi_upload(project, standardized_dir, dry_run=dry_run)
        return

    if script_changed:
        log.info(
            "[%s] conversion script changed (%s -> %s); reprocessing all %d discovered session(s)",
            project.lab,
            state.script_sha256,
            current_script_hash,
            len(discovered),
        )
    else:
        log.info("[%s] %d new session(s): %s", project.lab, len(new_sessions), ", ".join(new_sessions))

    convert(
        project,
        repo_root=repo_root,
        incoming_dir=incoming_dir,
        standardized_dir=standardized_dir,
        force_overwrite=script_changed,
        dry_run=dry_run,
    )

    session_glob_prefix = project.session_glob.split("*", 1)[0]  # dir portion before the first wildcard
    converted_at = now_iso()
    for session_id in discovered if script_changed else new_sessions:
        state.mark_converted(
            session_id,
            source_path=str(incoming_dir / session_glob_prefix / session_id),
            converted_at=converted_at,
        )
    if current_script_hash is not None:
        state.script_sha256 = current_script_hash
    state.last_run_at = converted_at
    touched = discovered if script_changed else new_sessions
    if not dry_run:
        state.save(standardized_dir)
    else:
        log.info("[%s] [dry-run] would write state for %d session(s)", project.lab, len(touched))

    if not skip_upload:
        dandi_upload(project, standardized_dir, dry_run=dry_run)


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
        help="Path to projects.yaml (default: <repo-root>/dispatch/projects.yaml).",
    )
    parser.add_argument(
        "--incoming-root",
        type=Path,
        required=True,
        help="Top-level 'ember-incoming' folder of local dandiset copies.",
    )
    parser.add_argument(
        "--standardized-root",
        type=Path,
        required=True,
        help="Top-level 'ember-standardized' folder for converted output.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help="Restrict to this lab name (repeatable). Default: all registered projects.",
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

    registry_path = args.registry or (args.repo_root / "dispatch" / "projects.yaml")
    projects = load_registry(registry_path)
    if args.only:
        wanted = set(args.only)
        projects = [p for p in projects if p.lab in wanted]
        missing = wanted - {p.lab for p in projects}
        if missing:
            log.error("--only named unknown lab(s): %s", ", ".join(sorted(missing)))
            return 2

    failures = []
    for project in projects:
        try:
            process_project(
                project,
                repo_root=args.repo_root,
                incoming_root=args.incoming_root,
                standardized_root=args.standardized_root,
                skip_download=args.skip_download,
                skip_upload=args.skip_upload,
                dry_run=args.dry_run,
            )
        except Exception:
            log.exception("[%s] failed; continuing with remaining projects", project.lab)
            failures.append(project.lab)

    if failures:
        log.error("failed project(s): %s", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
