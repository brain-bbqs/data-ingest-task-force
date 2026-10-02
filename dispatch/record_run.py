#!/usr/bin/env python3
"""Run a command and write a manifest of the files it created or changed.

dispatch.py runs each conversion through this script, inside the lab's own
container, as part of a ``datalad containers-run`` in the tracking dataset.
The manifest therefore lands in that run's own commit, next to con-duct's
logs. It lists every file under --root that is new or changed (by size or
mtime) after the command ran, with its size and sha256, plus any file that
disappeared.

Standard library only, and kept to Python 3.8 syntax, since it runs under
whatever python3 a lab image ships.

    python3 record_run.py --cwd DIR --root DIR --manifest PATH -- CMD [ARGS...]

Exits with the command's own exit code. The manifest is written either way.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def snapshot(root: str, /) -> dict:
    """(size, mtime_ns) of every non-hidden file under *root*. Hidden files
    and directories (dispatch's .ingest_state.json, dandi's caches) are
    bookkeeping, not output."""
    files = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            if filename.startswith("."):
                continue
            path = os.path.join(dirpath, filename)
            stat = os.stat(path)
            files[os.path.relpath(path, root)] = (stat.st_size, stat.st_mtime_ns)
    return files


def sha256(path: str, /) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cwd", required=True, help="Working directory for the command.")
    parser.add_argument("--root", required=True, help="Output directory to diff before and after the command.")
    parser.add_argument("--manifest", required=True, help="Where to write the manifest JSON.")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="The command to run, after '--'.")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command given")

    before = snapshot(args.root) if os.path.isdir(args.root) else {}
    started_at = now_iso()
    exit_code = subprocess.call(command, cwd=args.cwd)
    finished_at = now_iso()
    after = snapshot(args.root) if os.path.isdir(args.root) else {}

    written = sorted(path for path, stat in after.items() if before.get(path) != stat)
    manifest = {
        "command": command,
        "exit_code": exit_code,
        "started_at": started_at,
        "finished_at": finished_at,
        "root": args.root,
        "written": [
            {"path": path, "size": after[path][0], "sha256": sha256(os.path.join(args.root, path))} for path in written
        ],
        "removed": sorted(set(before) - set(after)),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.manifest)), exist_ok=True)
    with open(args.manifest, "w") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
