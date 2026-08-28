import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dispatch/

from registry import DEFAULT_DANDI_INSTANCE, RegistryError, load_registry  # noqa: E402

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
    assert kemere.standardized_dandiset_id == "000525"
    assert kemere.overwrite_flag == "--overwrite"
    assert kemere.container_image == "ghcr.io/brain-bbqs/kemere-r34da059514-ingest:latest"
    assert kemere.metadata == {"species": "Ovis aries"}


def test_committed_projects_all_use_the_default_dandi_instance():
    projects = load_registry(Path(__file__).resolve().parents[1] / "projects.json")
    assert [p.dandi_instance for p in projects] == [DEFAULT_DANDI_INSTANCE] * len(projects)


def test_valid_minimal_entry(tmp_path):
    path = write_registry(tmp_path, {"projects": [entry()]})
    (project,) = load_registry(path)
    assert project.lab == "test-lab"
    assert project.dandi_instance == DEFAULT_DANDI_INSTANCE  # default
    assert project.overwrite_flag is None
    assert project.container_image is None  # default: run directly on the runner host
    assert project.metadata == {}  # default: no project-wide placeholders


def test_container_image_is_read_when_present(tmp_path):
    path = write_registry(tmp_path, {"projects": [entry(container_image="ghcr.io/example/lab-ingest:latest")]})
    (project,) = load_registry(path)
    assert project.container_image == "ghcr.io/example/lab-ingest:latest"


def test_metadata_is_read_when_present(tmp_path):
    path = write_registry(tmp_path, {"projects": [entry(metadata={"species": "Mus musculus"})]})
    (project,) = load_registry(path)
    assert project.metadata == {"species": "Mus musculus"}


def test_metadata_shadowing_reserved_placeholder_raises(tmp_path):
    path = write_registry(tmp_path, {"projects": [entry(metadata={"incoming_dir": "nope"})]})
    with pytest.raises(RegistryError, match="shadow"):
        load_registry(path)


def test_non_object_metadata_raises(tmp_path):
    path = write_registry(tmp_path, {"projects": [entry(metadata=["not", "a", "dict"])]})
    with pytest.raises(RegistryError, match="metadata must be an object"):
        load_registry(path)


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


def test_project_key_is_the_lab_when_no_project_is_named(tmp_path):
    path = write_registry(tmp_path, {"projects": [entry()]})
    (project,) = load_registry(path)
    assert project.project is None
    assert project.key == "test-lab"


def test_project_key_combines_lab_and_project_when_named(tmp_path):
    path = write_registry(tmp_path, {"projects": [entry(project="in-lab")]})
    (project,) = load_registry(path)
    assert project.project == "in-lab"
    assert project.key == "test-lab/in-lab"


def test_one_lab_may_register_several_projects(tmp_path):
    path = write_registry(
        tmp_path,
        {
            "projects": [
                entry(project="in-lab", incoming_dandiset_id="000001", standardized_dandiset_id="000002"),
                entry(project="at-home", incoming_dandiset_id="000003", standardized_dandiset_id="000004"),
            ]
        },
    )
    projects = load_registry(path)
    assert [p.key for p in projects] == ["test-lab/in-lab", "test-lab/at-home"]


def test_duplicate_project_key_raises(tmp_path):
    path = write_registry(
        tmp_path,
        {
            "projects": [
                entry(project="in-lab", incoming_dandiset_id="000001", standardized_dandiset_id="000002"),
                entry(project="in-lab", incoming_dandiset_id="000003", standardized_dandiset_id="000004"),
            ]
        },
    )
    with pytest.raises(RegistryError, match="registered more than once"):
        load_registry(path)


@pytest.mark.parametrize("bad_project", ["", "in/lab", 7])
def test_malformed_project_raises(tmp_path, bad_project):
    path = write_registry(tmp_path, {"projects": [entry(project=bad_project)]})
    with pytest.raises(RegistryError, match="project"):
        load_registry(path)


def test_load_registry_reads_the_committed_suthana_in_lab_project():
    projects = load_registry(Path(__file__).resolve().parents[1] / "projects.json")
    suthana = next(p for p in projects if p.key == "suthana/in-lab")
    assert suthana.lab == "suthana"
    assert suthana.project == "in-lab"
    assert suthana.incoming_dandiset_id == "000530"
    assert suthana.standardized_dandiset_id == "000531"
