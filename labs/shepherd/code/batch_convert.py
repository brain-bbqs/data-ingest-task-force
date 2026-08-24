#!/usr/bin/env python3
"""Batch driver for the Shepherd session-to-NWB conversion.

Discovers every session folder under an incoming directory tree's
``sourcedata/raw/sessions/`` (one folder per session, each holding
``digital/``, ``analog/``, ``videos/``, and ``pose_estimation/`` subfolders
-- see ``code/README.md``) and runs ``shepherd_to_nwb.build_nwb`` on each,
writing the results into the standardized output tree::

    <output>/
      sub-<subject>/
        sub-<subject>_ses-<session>_desc-raw.nwb
        sub-<subject>_ses-<session>_desc-processed.nwb

``shepherd_to_nwb.py`` is a verbatim port of the original conversion work and
is deliberately not edited (see ``labs/shepherd/README.md``), so it carries
no ``__init__.py``/package structure. This module imports it by inserting
its own directory onto ``sys.path`` rather than adding one.

Subject and session identity: there is no established naming convention yet
for real Shepherd session folders (unlike Inman's parseable walk filenames).
Matching the original hard-coded example (folder ``sample-1`` ->
``--subject XYZ --session 1``), each session folder's sanitized name becomes
the subject label and the session is fixed at "1" -- one folder is one
session. This is a placeholder pending the lab's real naming convention.

Discovery looks under ``sourcedata/raw/sessions/`` rather than directly under
``sourcedata/raw/`` because the dandiset currently registered for Shepherd
holds data in a different, pre-existing shape (per-subject video/NWB files,
not the ``digital``/``analog``/``videos``/``pose_estimation`` layout above).
That data is left alone under ``sourcedata/raw/`` and is not real input for
this converter, so nesting discovery one level down means it currently finds
zero sessions -- the same "no data yet" state as a freshly registered
project -- until real Shepherd sessions are uploaded into
``sourcedata/raw/sessions/``.

``config.yaml`` supplies one global ``session_start_time`` and one global set
of subject metadata (species/age/sex) for every session, a known rough edge
(see the README) left as-is here rather than fixed as part of adding this
driver.

Outputs that already exist are skipped unless ``--overwrite`` is given. A
session counts as already converted only when *both* its raw and processed
NWB files are present; a half-written pair (one file present, one not) is
treated as incomplete and reconverted regardless of ``--overwrite``.
Dispatch (``dispatch/projects.json``) relies on the flag. It re-runs this
script whenever new sessions appear in the incoming dandiset, and appends
``--overwrite`` when the core conversion script has changed.

Sessions are converted one at a time, not in parallel: ``shepherd_to_nwb.py``
fully decodes every video into memory before writing it (a documented rough
edge), so running several sessions concurrently would multiply that memory
pressure rather than just speed things up.

A failed session does not stop the batch. The remaining sessions are still
converted and the exit code reports whether any failed.

Example CLI usage (from the repository root)
--------------------------------------------
python3 labs/shepherd/code/batch_convert.py \\
    --input ember-incoming/000528 --output ember-standardized/000529 \\
    --config labs/shepherd/code/config.yaml
"""

import argparse
import re
import sys
import traceback
from pathlib import Path

import tqdm

# shepherd_to_nwb.py is a verbatim, deliberately unedited port (see
# labs/shepherd/README.md) with no __init__.py to make it a package, so
# import it by name after putting this file's own directory on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shepherd_to_nwb import build_nwb, load_cfg  # noqa: E402


def sanitize_label(text, /):
    """Reduce *text* to an alphanumeric label usable in sub-/ses- names."""
    label = re.sub(r"[^0-9A-Za-z]", "", text)
    return label


def discover_sessions(incoming_dir, /):
    """Every session folder under *incoming_dir*'s ``sourcedata/raw/sessions/``
    as ``(session_dir, subject)``.

    There is no established naming convention for real session folders yet,
    so each folder's sanitized name becomes the subject label. Nested one
    level below ``sourcedata/raw/`` because that directory currently holds
    data in a different, pre-existing shape that this converter cannot read.
    """
    raw_dir = incoming_dir / "sourcedata" / "raw" / "sessions"
    if not raw_dir.is_dir():
        return []
    sessions = []
    for session_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        subject = sanitize_label(session_dir.name) or "unknown"
        sessions.append((session_dir, subject))
    return sessions


def output_stem(*, standardized_dir, subject, session):
    return standardized_dir / f"sub-{subject}" / f"sub-{subject}_ses-{session}"


def is_complete(stem, /):
    return Path(f"{stem}_desc-raw.nwb").is_file() and Path(f"{stem}_desc-processed.nwb").is_file()


def convert_batch(*, incoming_dir, standardized_dir, config_path, overwrite=False):
    cfg = load_cfg(config_path)
    sessions = discover_sessions(incoming_dir)
    if not sessions:
        print(f"No session folders found under {incoming_dir / 'sourcedata' / 'raw' / 'sessions'}")
        return 0

    skipped = 0
    pending = []
    for session_dir, subject in sessions:
        session = "1"
        stem = output_stem(standardized_dir=standardized_dir, subject=subject, session=session)
        if is_complete(stem) and not overwrite:
            print(f"Exists, skipping (use --overwrite): {stem}", flush=True)
            skipped += 1
            continue
        pending.append((session_dir, subject, session, stem))

    converted = 0
    failed = []
    for session_dir, subject, session, stem in tqdm.tqdm(pending, desc="Converting sessions", unit="session"):
        stem.parent.mkdir(parents=True, exist_ok=True)
        try:
            build_nwb(input_file=str(session_dir), subject_name=subject, out_nwb=str(stem), cfg=cfg)
        except Exception as error:
            traceback.print_exception(error)
            print(f"FAILED: {session_dir}: {error}", file=sys.stderr, flush=True)
            failed.append(session_dir)
            continue
        converted += 1
        tqdm.tqdm.write(f"Converted {session_dir} (subject {subject}, session {session}) -> {stem}")

    print(f"Converted {converted}, skipped {skipped}, failed {len(failed)} of {len(sessions)} session(s)", flush=True)
    exit_code = 1 if failed else 0
    return exit_code


def parse_args():
    parser = argparse.ArgumentParser(description="Convert every Shepherd session folder under a directory to NWB")
    parser.add_argument("--input", required=True, type=Path, help="Incoming directory holding sourcedata/raw/")
    parser.add_argument("--output", required=True, type=Path, help="Standardized output directory for NWB files")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.yaml",
        help="YAML config (default: config.yaml next to this script)",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Reconvert sessions whose output NWB pair already exists"
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
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
