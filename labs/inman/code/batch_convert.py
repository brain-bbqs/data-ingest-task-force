#!/usr/bin/env python3
"""Batch driver for the Inman .mat-to-NWB conversion.

Discovers every ``.mat`` walk file under an incoming directory tree (one
folder per session, e.g. ``sample-1/``) and runs ``inman_to_nwb.build_nwb``
on each, writing the results into the standardized output tree described in
``code/README.md``::

    <output>/
      sub-<subject>/
        ses-walk<N>/
          sub-<subject>_ses-walk<N>_behavior+ecephys.nwb

Subject and walk numbers are parsed from filenames like
``RWNApp_RW3_Walk1_restructured.mat`` (subject 3, walk 1). A file whose name
does not match falls back to its folder name as the subject label and its
sort position within that folder as the walk number.

Outputs that already exist are skipped unless ``--overwrite`` is given.
Dispatch (``dispatch/projects.json``) relies on this. It re-runs this script
whenever new sessions appear in the incoming dandiset, and appends
``--overwrite`` when the core conversion script has changed.

A failed file does not stop the batch. The remaining files are still
converted and the exit code reports whether any failed.

Example CLI usage
-----------------
python3 batch_convert.py --input ember-incoming/000519 \\
    --output ember-standardized/000526 --config ./config.yaml
"""

import argparse
import re
import sys
import traceback
from pathlib import Path

import inman_to_nwb
import pymatreader

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
    session = f"walk{walk}"
    nwb_path = (
        standardized_dir / f"sub-{subject}" / f"ses-{session}" / f"sub-{subject}_ses-{session}_behavior+ecephys.nwb"
    )
    return nwb_path


def convert_walk(*, mat_path, subject, walk, out_nwb, cfg):
    data = pymatreader.read_mat(mat_path, variable_names=inman_to_nwb.READ_KEYS)
    missing = [key for key in inman_to_nwb.REQUIRED_KEYS if key not in data]
    if missing:
        raise ValueError(f"missing keys in MAT data: {missing}")
    out_nwb.parent.mkdir(parents=True, exist_ok=True)
    inman_to_nwb.build_nwb(data=data, subject_name=subject, session=walk, out_nwb=out_nwb, cfg=cfg)


def convert_batch(*, incoming_dir, standardized_dir, config_path, overwrite=False):
    cfg = inman_to_nwb.load_cfg(config_path)
    walks = discover_walks(incoming_dir)
    if not walks:
        print(f"No .mat files found under {incoming_dir}")
        return 0

    converted = 0
    skipped = 0
    failed = []
    for mat_path, subject, walk in walks:
        out_nwb = output_path(standardized_dir=standardized_dir, subject=subject, walk=walk)
        if out_nwb.is_file() and not overwrite:
            print(f"Exists, skipping (use --overwrite): {out_nwb}", flush=True)
            skipped += 1
            continue
        print(f"Converting {mat_path} (subject {subject}, walk {walk}) -> {out_nwb}", flush=True)
        try:
            convert_walk(mat_path=mat_path, subject=subject, walk=walk, out_nwb=out_nwb, cfg=cfg)
        except Exception as error:
            traceback.print_exc()
            print(f"FAILED: {mat_path}: {error}", file=sys.stderr, flush=True)
            failed.append(mat_path)
            continue
        converted += 1

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
    arguments = parser.parse_args()
    return arguments


def main():
    args = parse_args()
    exit_code = convert_batch(
        incoming_dir=args.input,
        standardized_dir=args.output,
        config_path=args.config,
        overwrite=args.overwrite,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
