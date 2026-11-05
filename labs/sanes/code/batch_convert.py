#!/usr/bin/env python3
"""Batch driver for every Sanes dataset's session-to-NWB conversion.

Discovers every session folder (a folder holding ``idx_*`` chunk folders) directly under ``--input`` or
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

Example CLI usage (from the repository root)
--------------------------------------------
python3 labs/sanes/code/batch_convert.py \\
    --input ember-incoming/000522/sourcedata/raw --output ember-standardized/000523 \\
    --config labs/sanes/code/config.yaml
"""

import argparse
import sys
import traceback
from pathlib import Path

import tqdm

# _sanes_to_nwb.py sits next to this file in a directory that is not an importable package path, so put
# that directory on sys.path and import the sibling by name.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _sanes_to_nwb import build_nwb, load_cfg, multisubject_path  # noqa: E402


def _holds_chunks(directory, /):
    holds = any(path.is_dir() and path.name.startswith("idx_") for path in directory.iterdir())
    return holds


def discover_sessions(input_dir, /):
    """Session folders directly under *input_dir* or one folder below it, plus the folders that held none."""
    sessions = []
    ignored = []
    if not input_dir.is_dir():
        return sessions, ignored
    for candidate in sorted(path for path in input_dir.iterdir() if path.is_dir()):
        if _holds_chunks(candidate):
            sessions.append(candidate)
            continue
        nested = sorted(path for path in candidate.iterdir() if path.is_dir() and _holds_chunks(path))
        if nested:
            sessions.extend(nested)
        else:
            ignored.append(candidate)
    return sessions, ignored


def convert_batch(*, incoming_dir, standardized_dir, config_path, overwrite=False):
    cfg = load_cfg(config_path)
    output_dir = standardized_dir / cfg.get("output_subdirectory", "")
    sessions, ignored = discover_sessions(incoming_dir)
    for candidate in ignored:
        print(f"Ignoring (no idx_* chunk folders): {candidate}", flush=True)
    if not sessions:
        print(f"No session folders found under {incoming_dir}")
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
    failed = []
    for session_dir in tqdm.tqdm(pending, desc="Converting sessions", unit="session"):
        try:
            output_path = build_nwb(session_dir=session_dir, output_dir=output_dir, config_path=config_path)
        except Exception as error:
            traceback.print_exception(error)
            print(f"FAILED: {session_dir}: {error}", file=sys.stderr, flush=True)
            failed.append(session_dir)
            continue
        converted += 1
        tqdm.tqdm.write(f"Converted {session_dir} -> {output_path}")

    print(f"Converted {converted}, skipped {skipped}, failed {len(failed)} of {len(sessions)} session(s)", flush=True)
    exit_code = 1 if failed else 0
    return exit_code


def main():
    parser = argparse.ArgumentParser(description="Convert every Sanes session folder under a directory to NWB")
    parser.add_argument("--input", dest="input_dir", type=Path, required=True, help="Folder holding the sessions")
    parser.add_argument("--output", dest="output_dir", type=Path, required=True, help="Standardized dandiset folder")
    parser.add_argument("--config", type=Path, required=True, help="The dataset's config in labs/sanes/code/")
    parser.add_argument("--overwrite", action="store_true", help="Reconvert sessions whose output already exists")
    args = parser.parse_args()
    exit_code = convert_batch(
        incoming_dir=args.input_dir, standardized_dir=args.output_dir, config_path=args.config, overwrite=args.overwrite
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
