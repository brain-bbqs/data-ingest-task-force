"""The one place dispatch starts a subprocess, so --dry-run is honored the
same way for every external command."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger("dispatch")


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, dry_run: bool) -> None:
    printable = " ".join(cmd)
    if dry_run:
        log.info("[dry-run] would run: %s%s", printable, f"  (cwd={cwd})" if cwd else "")
        return
    log.info("running: %s%s", printable, f"  (cwd={cwd})" if cwd else "")
    subprocess.run(cmd, cwd=cwd, env=env, check=True)
