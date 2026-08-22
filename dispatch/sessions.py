"""Per-lab session discovery spec (dispatch/sessions.json).

Kept separate from projects.json's dandiset/command config because
discovering "what counts as a session" doesn't reduce to a single glob in
general -- a lab may need multiple include patterns (several raw subtrees)
and exclusions (stray non-session directories), and that shape can evolve
independently of a project's dandiset ids or conversion command.
"""

from __future__ import annotations

import fnmatch
import glob
import json
from dataclasses import dataclass, field
from pathlib import Path


class SessionSpecError(ValueError):
    pass


@dataclass
class SessionSpec:
    include: list[str]
    exclude: list[str] = field(default_factory=list)


def load_session_specs(path: Path) -> dict[str, SessionSpec]:
    payload = json.loads(path.read_text()) or {}
    raw_labs = payload.get("labs", {})
    if not raw_labs:
        raise SessionSpecError(f"{path} defines no labs")

    specs: dict[str, SessionSpec] = {}
    for lab, raw in raw_labs.items():
        include = raw.get("include")
        if not include or not isinstance(include, list):
            raise SessionSpecError(f"sessions.json entry for lab {lab!r} needs a non-empty 'include' list")
        specs[lab] = SessionSpec(include=list(include), exclude=list(raw.get("exclude", [])))
    return specs


def discover_sessions(incoming_dir: Path, spec: SessionSpec) -> list[Path]:
    """Session directories matched by any of spec.include and none of
    spec.exclude. A session is a directory (stray files alongside them are
    ignored); the session id is its basename (Path.name).

    Exclude patterns are matched against either the basename or the path
    relative to incoming_dir, so a lab can exclude by name ("*-ignore*") or
    by location ("sourcedata/raw/tmp-*").
    """
    matched: dict[str, Path] = {}
    for pattern in spec.include:
        for match in glob.glob(str(incoming_dir / pattern)):
            path = Path(match)
            if path.is_dir():
                matched[path.name] = path

    def is_excluded(name: str, path: Path) -> bool:
        relative = path.relative_to(incoming_dir).as_posix()
        return any(fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(relative, pat) for pat in spec.exclude)

    return sorted((p for name, p in matched.items() if not is_excluded(name, p)), key=lambda p: p.name)
