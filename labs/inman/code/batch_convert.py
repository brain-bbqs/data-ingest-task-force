#!/usr/bin/env python3
"""Batch driver for the Inman .mat-to-NWB conversion.

Discovers every ``.mat`` walk file under an incoming directory tree (one
folder per session, e.g. ``sample-1/``) and runs ``_inman_to_nwb.build_nwb``
on each, writing the results into the standardized output tree described in
``code/README.md``::

    <output>/
      sub-<subject>/
        sub-<subject>_ses-walk<N>_behavior+ecephys.nwb

Subject and walk numbers are parsed from filenames like
``RWNApp_RW3_Walk1_restructured.mat`` (subject 3, walk 1). A file whose name
does not match falls back to its folder name as the subject label and its
sort position within that folder as the walk number.

Outputs that already exist are skipped unless ``--overwrite`` is given.
Dispatch (``dispatch/projects.json``) relies on this. It re-runs this script
whenever new sessions appear in the incoming dandiset, and appends
``--overwrite`` when the core conversion script has changed.

Walk files are converted in parallel, one worker process per CPU by
default (``--jobs`` overrides that), with a tqdm bar tracking completions.

A failed file does not stop the batch. The remaining files are still
converted and the exit code reports whether any failed.

Example CLI usage (from the repository root, so the package resolves)
---------------------------------------------------------------------
python3 -m labs.inman.code.batch_convert --input ember-incoming/000519 \\
    --output ember-standardized/000526 --config labs/inman/code/config.yaml
"""

import argparse
import concurrent.futures
import multiprocessing
import os
import re
import sys
import traceback
from pathlib import Path

import pymatreader
import tqdm

from ._inman_to_nwb import READ_KEYS, REQUIRED_KEYS, build_nwb, load_cfg

WALK_FILENAME_PATTERN = re.compile(r"RW(?P<subject>\d+)_Walk(?P<walk>\d+)", re.IGNORECASE)


def sanitize_label(text, /):
    """Reduce *text* to an alphanumeric label usable in sub-/ses- names."""
    label = re.sub(r"[^0-9A-Za-z]", "", text)
    return label


def parse_walk_identity(mat_path, /):
    """(subject, walk) parsed from a walk filename, or ``None`` if it doesn't match."""
    match = WALK_FILENAME_PATTERN.search(mat_path.stem)
    if match is None:
        return None
    identity = (match["subject"], int(match["walk"]))
    return identity


def discover_walks(incoming_dir, /):
    """Every ``.mat`` file under *incoming_dir* as ``(mat_path, subject, walk)``.

    Files whose names don't carry a subject/walk fall back to their folder
    name as the subject and a per-folder 1-based counter as the walk, so
    sample uploads (e.g. ``sample-1/``) still convert deterministically.
    """
    walks = []
    fallback_counts: dict[Path, int] = {}
    for mat_path in sorted(incoming_dir.rglob("*.mat")):
        identity = parse_walk_identity(mat_path)
        if identity is None:
            folder = mat_path.parent
            fallback_counts[folder] = fallback_counts.get(folder, 0) + 1
            fallback_name = folder.name if folder != incoming_dir else mat_path.stem
            subject = sanitize_label(fallback_name) or "unknown"
            identity = (subject, fallback_counts[folder])
        walks.append((mat_path, *identity))
    return walks


def output_path(*, standardized_dir, subject, walk):
    # DANDI layout keeps assets directly under sub-<subject>/ (a ses-
    # subfolder fails dandi validation with NON_DANDI_FOLDERNAME).
    session = f"walk{walk}"
    nwb_path = standardized_dir / f"sub-{subject}" / f"sub-{subject}_ses-{session}_behavior+ecephys.nwb"
    return nwb_path


def remove_legacy_output(*, standardized_dir, subject, walk):
    """Outputs briefly landed in a ses- subfolder, which dandi validation
    rejects (NON_DANDI_FOLDERNAME). Remove that variant wherever it still
    exists so it cannot fail future uploads of the standardized directory."""
    session = f"walk{walk}"
    legacy_dir = standardized_dir / f"sub-{subject}" / f"ses-{session}"
    legacy_nwb = legacy_dir / f"sub-{subject}_ses-{session}_behavior+ecephys.nwb"
    if legacy_nwb.is_file():
        print(f"Removing legacy nested output: {legacy_nwb}", flush=True)
        legacy_nwb.unlink()
        try:
            legacy_dir.rmdir()
        except OSError:
            pass


def convert_walk(*, mat_path, subject, walk, out_nwb, cfg):
    data = pymatreader.read_mat(mat_path, variable_names=READ_KEYS)
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise ValueError(f"missing keys in MAT data: {missing}")
    out_nwb.parent.mkdir(parents=True, exist_ok=True)
    build_nwb(data=data, subject_name=subject, session=walk, out_nwb=out_nwb, cfg=cfg)


def resolve_worker_count(*, requested, task_count):
    """How many worker processes to run *task_count* conversions across.

    ``requested`` of ``None`` means one worker per CPU. The count is always
    capped at the number of tasks, so a single walk never spawns a pool of
    idle workers.
    """
    available = requested if requested is not None else os.cpu_count() or 1
    worker_count = max(1, min(available, task_count))
    return worker_count


def convert_batch(*, incoming_dir, standardized_dir, config_path, overwrite=False, max_workers=None):
    cfg = load_cfg(config_path)
    walks = discover_walks(incoming_dir)
    if not walks:
        print(f"No .mat files found under {incoming_dir}")
        return 0

    skipped = 0
    pending = []
    for mat_path, subject, walk in walks:
        remove_legacy_output(standardized_dir=standardized_dir, subject=subject, walk=walk)
        out_nwb = output_path(standardized_dir=standardized_dir, subject=subject, walk=walk)
        if out_nwb.is_file() and not overwrite:
            print(f"Exists, skipping (use --overwrite): {out_nwb}", flush=True)
            skipped += 1
            continue
        pending.append((mat_path, subject, walk, out_nwb))

    converted = 0
    failed = []
    if pending:
        worker_count = resolve_worker_count(requested=max_workers, task_count=len(pending))
        print(f"Converting {len(pending)} walk file(s) across {worker_count} worker(s)", flush=True)
        # Each walk is an independent read-then-write of one .mat file, so
        # separate processes sidestep the GIL that would otherwise serialize
        # the NWB assembly. They are started with "spawn" rather than the
        # Linux default: forking an interpreter that has already loaded the
        # HDF5 stack copies its threads' locks into the child, where they can
        # deadlock.
        spawn_context = multiprocessing.get_context("spawn")
        with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count, mp_context=spawn_context) as executor:
            futures = {}
            for mat_path, subject, walk, out_nwb in pending:
                future = executor.submit(
                    convert_walk, mat_path=mat_path, subject=subject, walk=walk, out_nwb=out_nwb, cfg=cfg
                )
                futures[future] = (mat_path, subject, walk, out_nwb)
            completed = concurrent.futures.as_completed(futures)
            for future in tqdm.tqdm(completed, total=len(futures), desc="Converting walks", unit="walk"):
                mat_path, subject, walk, out_nwb = futures[future]
                try:
                    future.result()
                except Exception as error:
                    traceback.print_exception(error)
                    print(f"FAILED: {mat_path}: {error}", file=sys.stderr, flush=True)
                    failed.append(mat_path)
                    continue
                converted += 1
                tqdm.tqdm.write(f"Converted {mat_path} (subject {subject}, walk {walk}) -> {out_nwb}")

    print(f"Converted {converted}, skipped {skipped}, failed {len(failed)} of {len(walks)} walk file(s)", flush=True)
    exit_code = 1 if failed else 0
    return exit_code


def parse_args():
    parser = argparse.ArgumentParser(description="Convert every Inman .mat walk file under a directory to NWB")
    parser.add_argument("--input", required=True, type=Path, help="Incoming directory holding walk session folders")
    parser.add_argument("--output", required=True, type=Path, help="Standardized output directory for NWB files")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.yaml",
        help="YAML config (default: config.yaml next to this script)",
    )
    parser.add_argument("--overwrite", action="store_true", help="Reconvert walks whose output NWB already exists")
    parser.add_argument(
        "--jobs",
        type=int,
        default=None,
        help="Walk files to convert in parallel (default: one per CPU, capped at the number of walks)",
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
