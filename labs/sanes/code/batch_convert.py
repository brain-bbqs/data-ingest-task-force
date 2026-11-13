#!/usr/bin/env python3
"""Batch driver for every Sanes dataset's session-to-NWB conversion.

Discovers session folders holding ``idx_*`` chunks or ``concatenated_data_cam_mic_sync/`` under ``--input`` or
one folder below it, and runs ``_sanes_to_nwb.build_nwb`` on each. The config picks the dataset, and its
optional ``output_subdirectory`` nests everything under one folder of ``--output``. R34 uses it because
that standardized dandiset already holds earlier, hand-made work at its root::

    <output>/[<output_subdirectory>/]
      sub-multi/
        sub-multi_ses-<session>_behavior.nwb   audio, combined video, vocalizations, SubjectsTable
        sub-multi_ses-<session>_video.mp4
      sub-<id>/
        sub-<id>_ses-<session>.nwb             one per tracked animal

Sessions whose multisubject file already exists are skipped unless ``--overwrite`` is given. Dispatch
appends it when the converter changes.

Sessions are converted one at a time, since each one stages its whole concatenated audio on disk next to
the output. A failed session does not stop the batch, and the exit code reports whether any failed.

An ``experiment_*`` folder with no supported layout is reported as pending, since its media may not be
uploaded yet, and does not fail the batch. So is a session whose ``sync.csv`` disagrees with its files (a
listed file missing, a malformed name, media timing outside ``sync.tolerance``), which waits on the lab to fix
the source data. With ``--results`` the batch writes the sessions it left
unconverted, as ``{"pending": {name: reason}, "failed": {name: reason}}`` keyed by folder name. Dispatch
fills it through its ``{results}`` placeholder, then keeps and uploads what did convert.

Example CLI usage (from the repository root)
--------------------------------------------
python3 labs/sanes/code/batch_convert.py \\
    --input ember-incoming/000522/sourcedata/raw --output ember-standardized/000523 \\
    --config labs/sanes/code/config.yaml
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

import tqdm

# _sanes_to_nwb.py sits next to this file in a directory that is not an importable package path, so put
# that directory on sys.path and import the sibling by name.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _sanes_to_nwb import (  # noqa: E402
    SYNC_FOLDER,
    SourceDataError,
    build_nwb,
    load_cfg,
    multisubject_path,
    session_label,
)

UNSUPPORTED_REASON = f"No idx_* chunks or {SYNC_FOLDER}/ folder yet"


def _subdirectories(directory, /):
    subdirectories = sorted(path for path in directory.iterdir() if path.is_dir())
    return subdirectories


def _holds_chunks(directory, /):
    holds = (directory / SYNC_FOLDER).is_dir() or any(
        path.is_dir() and path.name.startswith("idx_") for path in directory.iterdir()
    )
    return holds


def discover_sessions(input_dir, /):
    """Session folders directly under *input_dir* or one folder below it, plus the folders that held none."""
    sessions = []
    ignored = []
    if not input_dir.is_dir():
        return sessions, ignored
    for candidate in _subdirectories(input_dir):
        if _holds_chunks(candidate):
            sessions.append(candidate)
            continue
        nested = _subdirectories(candidate)
        found = [path for path in nested if _holds_chunks(path)]
        sessions.extend(found)
        ignored.extend([path for path in nested if path not in found] if found else [candidate])
    return sessions, ignored


def unsupported_experiments(ignored, /):
    """The ``experiment_*`` folders among *ignored*, or directly inside one of them."""
    experiments = []
    for path in ignored:
        if path.name.startswith("experiment_"):
            experiments.append(path)
        else:
            experiments.extend(child for child in _subdirectories(path) if child.name.startswith("experiment_"))
    return experiments


def write_results(path, /, *, pending, failed):
    results = {"pending": pending, "failed": failed}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")


def convert_batch(*, incoming_dir, standardized_dir, config_path, overwrite=False, results_path=None):
    cfg = load_cfg(config_path)
    output_dir = standardized_dir / cfg.get("output_subdirectory", "")
    sessions, ignored = discover_sessions(incoming_dir)
    for candidate in ignored:
        print(f"Ignoring (no supported recording layout): {candidate}", flush=True)
    unconverted = {path.name: UNSUPPORTED_REASON for path in unsupported_experiments(ignored)}
    for name in sorted(unconverted):
        print(f"PENDING: {name}: {UNSUPPORTED_REASON}", flush=True)
    labels = [session_label(session) for session in sessions]
    if len(set(labels)) != len(labels):
        print("FAILED: session labels collide after sanitization", file=sys.stderr, flush=True)
        return 1
    if not sessions:
        print(f"No session folders found under {incoming_dir}")
        if results_path is not None:
            write_results(results_path, pending=unconverted, failed={})
        return 0

    skipped = 0
    pending = []
    for session_dir in sessions:
        output_path = multisubject_path(output_dir=output_dir, session_dir=session_dir)
        if output_path.is_file() and not overwrite:
            print(f"Exists, skipping (use --overwrite): {output_path}", flush=True)
            skipped += 1
            continue
        pending.append(session_dir)

    converted = 0
    failed = {}
    for session_dir in tqdm.tqdm(pending, desc="Converting sessions", unit="session"):
        try:
            output_path = build_nwb(session_dir=session_dir, output_dir=output_dir, config_path=config_path)
        except SourceDataError as error:
            print(f"PENDING: {session_dir.name}: {error}", flush=True)
            unconverted[session_dir.name] = str(error)
            continue
        except Exception as error:
            traceback.print_exception(error)
            print(f"FAILED: {session_dir}: {error}", file=sys.stderr, flush=True)
            failed[session_dir.name] = str(error)
            continue
        converted += 1
        tqdm.tqdm.write(f"Converted {session_dir} -> {output_path}")

    print(f"Converted {converted}, skipped {skipped}, failed {len(failed)} of {len(sessions)} session(s)", flush=True)
    if results_path is not None:
        write_results(results_path, pending=unconverted, failed=failed)
    exit_code = 1 if failed else 0
    return exit_code


def main():
    parser = argparse.ArgumentParser(description="Convert every Sanes session folder under a directory to NWB")
    parser.add_argument("--input", dest="input_dir", type=Path, required=True, help="Folder holding the sessions")
    parser.add_argument("--output", dest="output_dir", type=Path, required=True, help="Standardized dandiset folder")
    parser.add_argument("--config", type=Path, required=True, help="The dataset's config in labs/sanes/code/")
    parser.add_argument("--overwrite", action="store_true", help="Reconvert sessions whose output already exists")
    parser.add_argument("--results", type=Path, default=None, help="Write the sessions left unconverted to this JSON")
    args = parser.parse_args()
    exit_code = convert_batch(
        incoming_dir=args.input_dir,
        standardized_dir=args.output_dir,
        config_path=args.config,
        overwrite=args.overwrite,
        results_path=args.results,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
