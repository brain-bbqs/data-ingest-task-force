import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dispatch/

from registry import RegistryError, load_registry  # noqa: E402

pytestmark = pytest.mark.ai_generated


def write_registry(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "projects.json"
    path.write_text(json.dumps(payload))
    return path


def entry(**overrides) -> dict:
    base = dict(
        lab="test-lab",
        incoming_dandiset_id="000001",
        standardized_dandiset_id="000002",
        script_path="labs/test-lab/code/convert.py",
        convert_command=["python3", "convert.py"],
    )
    base.update(overrides)
    return base


def test_load_registry_reads_the_committed_projects_json():
    projects = load_registry(Path(__file__).resolve().parents[1] / "projects.json")
    assert projects
    kemere = next(p for p in projects if p.lab == "kemere")
    assert kemere.incoming_dandiset_id == "000477"
    assert kemere.overwrite_flag == "--overwrite"
    assert kemere.container_image == "ghcr.io/brain-bbqs/kemere-r34da059514-ingest:latest"


def test_valid_minimal_entry(tmp_path):
    path = write_registry(tmp_path, {"projects": [entry()]})
    (project,) = load_registry(path)
    assert project.lab == "test-lab"
    assert project.dandi_instance == "emberarchive"  # default
    assert project.overwrite_flag is None
    assert project.container_image is None  # default: run directly on the runner host


def test_container_image_is_read_when_present(tmp_path):
    path = write_registry(tmp_path, {"projects": [entry(container_image="ghcr.io/example/lab-ingest:latest")]})
    (project,) = load_registry(path)
    assert project.container_image == "ghcr.io/example/lab-ingest:latest"


def test_missing_required_field_raises(tmp_path):
    path = write_registry(tmp_path, {"projects": [{"lab": "test-lab", "incoming_dandiset_id": "000001"}]})
    with pytest.raises(RegistryError, match="missing required field"):
        load_registry(path)


def test_non_six_digit_id_raises(tmp_path):
    path = write_registry(tmp_path, {"projects": [entry(incoming_dandiset_id="123")]})
    with pytest.raises(RegistryError, match="six-digit"):
        load_registry(path)


def test_duplicate_incoming_id_raises(tmp_path):
    path = write_registry(
        tmp_path,
        {
            "projects": [
                entry(lab="a", incoming_dandiset_id="000001", standardized_dandiset_id="000002"),
                entry(lab="b", incoming_dandiset_id="000001", standardized_dandiset_id="000003"),
            ]
        },
    )
    with pytest.raises(RegistryError, match="more than once"):
        load_registry(path)


def test_empty_projects_raises(tmp_path):
    path = write_registry(tmp_path, {"projects": []})
    with pytest.raises(RegistryError, match="no projects"):
        load_registry(path)
