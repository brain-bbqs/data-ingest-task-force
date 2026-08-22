"""Loads and validates the project registry (projects.json) that tells
dispatch.py which dandisets exist, how they map incoming -> standardized,
and how to run each lab's conversion script (optionally inside that lab's
published container image -- see container_image below).

Session discovery is deliberately not part of this file -- see sessions.py /
dispatch/sessions.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_FIELDS = (
    "lab",
    "incoming_dandiset_id",
    "standardized_dandiset_id",
    "script_path",
    "convert_command",
)

# Names convert_command tokens can already template; a metadata key reusing
# one would silently shadow it, so it's rejected at load time instead.
RESERVED_TEMPLATE_NAMES = ("repo_root", "incoming_dir", "standardized_dir")


class RegistryError(ValueError):
    pass


@dataclass
class Project:
    lab: str
    incoming_dandiset_id: str
    standardized_dandiset_id: str
    script_path: str
    convert_command: list[str]
    dandi_instance: str = "ember-dandi"
    overwrite_flag: str | None = None
    container_image: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def script_abspath(self, repo_root: Path) -> Path:
        return (repo_root / self.script_path).resolve()


def _validate_raw(raw: dict, *, index: int) -> None:
    label = f"projects.json entry #{index} ('{raw.get('lab')}')"
    missing = [field for field in REQUIRED_FIELDS if field not in raw]
    if missing:
        raise RegistryError(f"{label} is missing required field(s): {', '.join(missing)}")
    if not isinstance(raw["convert_command"], list) or not raw["convert_command"]:
        raise RegistryError(f"{label}: convert_command must be a non-empty list")
    for id_field in ("incoming_dandiset_id", "standardized_dandiset_id"):
        value = str(raw[id_field])
        if not (len(value) == 6 and value.isdigit()):
            raise RegistryError(f"{label}: {id_field}={value!r} is not a six-digit dandiset id")
    metadata = raw.get("metadata", {})
    if not isinstance(metadata, dict):
        raise RegistryError(f"{label}: metadata must be an object of string values")
    shadowed = set(metadata) & set(RESERVED_TEMPLATE_NAMES)
    if shadowed:
        raise RegistryError(f"{label}: metadata key(s) {sorted(shadowed)} shadow reserved convert_command placeholders")


def load_registry(path: Path) -> list[Project]:
    payload = json.loads(path.read_text()) or {}
    raw_projects = payload.get("projects", [])
    if not raw_projects:
        raise RegistryError(f"{path} defines no projects")

    projects: list[Project] = []
    seen_incoming: set[str] = set()
    for index, raw in enumerate(raw_projects):
        _validate_raw(raw, index=index)
        incoming_id = str(raw["incoming_dandiset_id"])
        if incoming_id in seen_incoming:
            raise RegistryError(f"projects.json: incoming_dandiset_id {incoming_id!r} is registered more than once")
        seen_incoming.add(incoming_id)
        projects.append(
            Project(
                lab=raw["lab"],
                incoming_dandiset_id=incoming_id,
                standardized_dandiset_id=str(raw["standardized_dandiset_id"]),
                script_path=raw["script_path"],
                convert_command=list(raw["convert_command"]),
                dandi_instance=raw.get("dandi_instance", "ember-dandi"),
                overwrite_flag=raw.get("overwrite_flag"),
                container_image=raw.get("container_image"),
                metadata=dict(raw.get("metadata", {})),
            )
        )
    return projects
