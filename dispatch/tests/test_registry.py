import sys
from pathlib import Path
from textwrap import dedent

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dispatch/

from registry import RegistryError, load_registry  # noqa: E402


def write_registry(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "projects.yaml"
    path.write_text(dedent(body))
    return path


def test_load_registry_reads_the_committed_projects_yaml():
    projects = load_registry(Path(__file__).resolve().parents[1] / "projects.yaml")
    assert projects
    kemere = next(p for p in projects if p.lab == "kemere")
    assert kemere.incoming_dandiset_id == "000477"
    assert kemere.session_glob == "sourcedata/raw/*-Session*"
    assert kemere.overwrite_flag == "--overwrite"


def test_valid_minimal_entry(tmp_path):
    path = write_registry(
        tmp_path,
        """\
        projects:
          - lab: test-lab
            incoming_dandiset_id: "000001"
            standardized_dandiset_id: "000002"
            session_glob: "raw/*"
            script_path: "labs/test-lab/code/convert.py"
            convert_command: ["python3", "{repo_root}/labs/test-lab/code/convert.py"]
        """,
    )
    (projects,) = load_registry(path)
    assert projects.lab == "test-lab"
    assert projects.dandi_instance == "emberarchive"  # default
    assert projects.overwrite_flag is None


def test_missing_required_field_raises(tmp_path):
    path = write_registry(
        tmp_path,
        """\
        projects:
          - lab: test-lab
            incoming_dandiset_id: "000001"
        """,
    )
    with pytest.raises(RegistryError, match="missing required field"):
        load_registry(path)


def test_non_six_digit_id_raises(tmp_path):
    path = write_registry(
        tmp_path,
        """\
        projects:
          - lab: test-lab
            incoming_dandiset_id: "123"
            standardized_dandiset_id: "000002"
            session_glob: "raw/*"
            script_path: "labs/test-lab/code/convert.py"
            convert_command: ["python3", "convert.py"]
        """,
    )
    with pytest.raises(RegistryError, match="six-digit"):
        load_registry(path)


def test_duplicate_incoming_id_raises(tmp_path):
    path = write_registry(
        tmp_path,
        """\
        projects:
          - lab: a
            incoming_dandiset_id: "000001"
            standardized_dandiset_id: "000002"
            session_glob: "raw/*"
            script_path: "labs/a/code/convert.py"
            convert_command: ["python3", "convert.py"]
          - lab: b
            incoming_dandiset_id: "000001"
            standardized_dandiset_id: "000003"
            session_glob: "raw/*"
            script_path: "labs/b/code/convert.py"
            convert_command: ["python3", "convert.py"]
        """,
    )
    with pytest.raises(RegistryError, match="more than once"):
        load_registry(path)


def test_empty_projects_raises(tmp_path):
    path = write_registry(tmp_path, "projects: []\n")
    with pytest.raises(RegistryError, match="no projects"):
        load_registry(path)
