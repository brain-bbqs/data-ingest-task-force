#!/usr/bin/env python3
"""Batch driver for the Zhang ferret hyperscanning conversion.

Discovers every recording directory under an incoming dandiset::

    <input>/sourcedata/raw/Ferret_Hyperscanning/<pair>/<MM.DD.YYYY>/<rec>.rec/

and runs ``_zhang_ferret_hyperscanning_to_nwb.convert_session`` on each,
writing two NWB files per recording (one per animal) plus the session's
videos into the DANDI layout described in ``code/README.md``.

A recording whose two NWB files already exist is skipped unless
``--overwrite`` is given. Dispatch (``dispatch/projects.json``) relies on
this: it re-runs this script whenever new recordings appear in the incoming
dandiset, and appends ``--overwrite`` when the core conversion script has
changed.

Recordings are converted in parallel across a small pool by default
(``--jobs`` overrides it). Memory is not the constraint, the ephys is a
memmap read, but every recording also copies about 170 GB of video into the
standardized tree unless the two directories share a filesystem and the
copy becomes a hard link, so a large pool would only contend for disk.

A failed recording does not stop the batch. The remaining recordings are
still converted and the exit code reports whether any failed.

Example CLI usage
-----------------
python3 labs/zhang/ferret-hyperscanning/code/batch_convert.py \\
    --input ember-incoming/000480 --output ember-standardized/000547 \\
    --config labs/zhang/ferret-hyperscanning/code/config.yaml
"""

from __future__ import annotations

import argparse
import concurrent.futures
import multiprocessing
import os
import sys
import traceback
from pathlib import Path

import tqdm

# The usual relative import of the sibling module is not available here: the
# project directory name (ferret-hyperscanning) has a hyphen, which is not a
# valid package name, so labs/zhang/ferret-hyperscanning/code/ is not an
# importable package path. Putting this file's own directory on sys.path
# imports the sibling by name instead. It runs again in every "spawn" worker,
# which re-imports this module by file path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _zhang_ferret_hyperscanning_to_nwb import (  # noqa: E402
    convert_session,
    load_cfg,
    load_session_log_for,
    output_paths,
    parse_rec_identity,
)

RAW_SUBTREE = Path("sourcedata") / "raw" / "Ferret_Hyperscanning"
SESSION_GLOB = "*/*/*.rec"
DEFAULT_JOBS = 2


def discover_recordings(incoming_dir, /):
    """Every ``.rec`` directory under the raw subtree of *incoming_dir*, plus the entries it ignored.

    Returns ``(recordings, ignored)``. A recording is a directory whose name
    ends in ``.rec`` two levels below the pair directories. ``ignored`` lists
    the other entries found alongside them (anything but the recording
    directories and the ``Videos/`` directory), so stray uploads are
    reported rather than silently skipped.
    """
    raw_root = Path(incoming_dir) / RAW_SUBTREE
    recordings = sorted(path for path in raw_root.glob(SESSION_GLOB) if path.is_dir())
    ignored = []
    for date_dir in sorted(path for path in raw_root.glob("*/*") if path.is_dir()):
        for entry in sorted(date_dir.iterdir()):
            if entry in recordings or entry.name == "Videos":
                continue
            ignored.append(entry)
    return recordings, ignored


def is_converted(*, rec_dir, standardized_dir):
    identity = parse_rec_identity(rec_dir)
    paths = output_paths(output_dir=standardized_dir, identity=identity)
    converted = all(path.is_file() for path in paths.values())
    return converted


def convert_recording(*, rec_dir, standardized_dir, config_path, overwrite):
    cfg = load_cfg(config_path)
    session_log = load_session_log_for(cfg, config_path=config_path)
    written = convert_session(
        rec=rec_dir, output_dir=standardized_dir, cfg=cfg, session_log=session_log, overwrite=overwrite
    )
    return written


def resolve_worker_count(*, requested, task_count):
    """How many worker processes to run *task_count* conversions across.

    ``requested`` of ``None`` means the small default, capped at the CPU
    count. The count is always capped at the number of tasks, so a single
    recording never spawns a pool of idle workers.
    """
    available = requested if requested is not None else min(DEFAULT_JOBS, os.cpu_count() or 1)
    worker_count = max(1, min(available, task_count))
    return worker_count


def convert_batch(*, incoming_dir, standardized_dir, config_path, overwrite=False, max_workers=None):
    incoming_dir = Path(incoming_dir)
    standardized_dir = Path(standardized_dir)
    recordings, ignored = discover_recordings(incoming_dir)
    for entry in ignored:
        print(f"Ignoring unexpected entry: {entry}", flush=True)
    if not recordings:
        print(f"No .rec recordings found under {incoming_dir / RAW_SUBTREE}")
        return 0

    skipped = 0
    pending = []
    for rec_dir in recordings:
        try:
            converted = is_converted(rec_dir=rec_dir, standardized_dir=standardized_dir)
        except ValueError as error:
            print(f"Ignoring unrecognized recording: {error}", flush=True)
            skipped += 1
            continue
        if converted and not overwrite:
            print(f"Exists, skipping (use --overwrite): {rec_dir.name}", flush=True)
            skipped += 1
            continue
        pending.append(rec_dir)

    converted = 0
    failed = []
    if pending:
        worker_count = resolve_worker_count(requested=max_workers, task_count=len(pending))
        print(f"Converting {len(pending)} recording(s) across {worker_count} worker(s)", flush=True)
        outcomes = _convert_pending(
            pending=pending,
            worker_count=worker_count,
            standardized_dir=standardized_dir,
            config_path=config_path,
            overwrite=overwrite,
        )
        for rec_dir, written, error in tqdm.tqdm(
            outcomes, total=len(pending), desc="Converting recordings", unit="rec"
        ):
            if error is not None:
                traceback.print_exception(error)
                print(f"FAILED: {rec_dir}: {error}", file=sys.stderr, flush=True)
                failed.append(rec_dir)
                continue
            converted += 1
            tqdm.tqdm.write(f"Converted {rec_dir.name} -> {', '.join(str(path) for path in written)}")

    print(
        f"Converted {converted}, skipped {skipped}, failed {len(failed)} of {len(recordings)} recording(s)", flush=True
    )
    exit_code = 1 if failed else 0
    return exit_code


def _convert_pending(*, pending, worker_count, standardized_dir, config_path, overwrite):
    """Yield ``(rec_dir, written_paths, error)`` per recording as each conversion completes.

    One worker runs in this process. More run in separate processes rather
    than threads, since the HDF5 stack serializes on the GIL, started with
    "spawn" rather than fork because forking an interpreter that has loaded
    HDF5 copies its threads' locks into the child.
    """
    kwargs = {"standardized_dir": standardized_dir, "config_path": config_path, "overwrite": overwrite}
    if worker_count == 1:
        for rec_dir in pending:
            try:
                yield rec_dir, convert_recording(rec_dir=rec_dir, **kwargs), None
            except Exception as error:
                yield rec_dir, None, error
        return
    spawn_context = multiprocessing.get_context("spawn")
    with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count, mp_context=spawn_context) as executor:
        futures = {executor.submit(convert_recording, rec_dir=rec_dir, **kwargs): rec_dir for rec_dir in pending}
        for future in concurrent.futures.as_completed(futures):
            rec_dir = futures[future]
            try:
                yield rec_dir, future.result(), None
            except Exception as error:
                yield rec_dir, None, error


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert every ferret hyperscanning recording under an incoming dandiset to NWB"
    )
    parser.add_argument("--input", required=True, type=Path, help="Incoming dandiset directory")
    parser.add_argument("--output", required=True, type=Path, help="Standardized output directory (DANDI layout)")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.yaml",
        help="YAML config (default: config.yaml next to this script)",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Reconvert recordings whose output files already exist"
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=None,
        help=f"Recordings to convert in parallel (default: {DEFAULT_JOBS}, capped at the CPU and recording counts)",
    )
    arguments = parser.parse_args()
    return arguments


def main():
    args = parse_args()
    exit_code = convert_batch(
        incoming_dir=args.input,
        standardized_dir=args.output,
        config_path=args.config,
        overwrite=args.overwrite,
        max_workers=args.jobs,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
