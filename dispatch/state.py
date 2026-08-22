"""Conversion-state manifest: tracks which sessions of a project have already
been converted, and with which revision of the conversion script, so cron runs
only redo work that's actually new.

One manifest lives at ``<standardized_dir>/.ingest_state.json`` per project
(next to the standardized/converted output, so it travels with it). It is
plain JSON, not uploaded to DANDI (see the upload step in dispatch.py, which
excludes dotfiles).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

STATE_FILENAME = ".ingest_state.json"


@dataclass
class IngestState:
    """In-memory view of a project's manifest."""

    script_sha256: str | None = None
    converted_sessions: dict[str, dict] = field(default_factory=dict)
    last_run_at: str | None = None

    @classmethod
    def load(cls, standardized_dir: Path) -> "IngestState":
        path = standardized_dir / STATE_FILENAME
        if not path.is_file():
            return cls()
        payload = json.loads(path.read_text())
        return cls(
            script_sha256=payload.get("script_sha256"),
            converted_sessions=payload.get("converted_sessions", {}),
            last_run_at=payload.get("last_run_at"),
        )

    def save(self, standardized_dir: Path) -> None:
        path = standardized_dir / STATE_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "script_sha256": self.script_sha256,
            "converted_sessions": self.converted_sessions,
            "last_run_at": self.last_run_at,
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def mark_converted(self, session_id: str, *, source_path: str, converted_at: str) -> None:
        self.converted_sessions[session_id] = {
            "source_path": source_path,
            "converted_at": converted_at,
        }

    def new_sessions(self, discovered_session_ids: list[str]) -> list[str]:
        """Sessions discovered on disk that have no manifest record yet."""
        return [sid for sid in discovered_session_ids if sid not in self.converted_sessions]


def hash_file(path: Path) -> str:
    """sha256 of a single file's contents, used to etag a conversion script."""
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()
