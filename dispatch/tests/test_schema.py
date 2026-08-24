"""Validates the committed registries against their JSON Schemas, and
exercises each schema against a couple of known-bad shapes so the schema
itself stays honest (not just "always passes")."""

import json
import sys
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dispatch/

pytestmark = pytest.mark.ai_generated

DISPATCH_DIR = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    return json.loads((DISPATCH_DIR / name).read_text())


def test_committed_projects_json_matches_its_schema():
    jsonschema.validate(instance=load("projects.json"), schema=load("schemas/projects.schema.json"))


def test_committed_sessions_json_matches_its_schema():
    jsonschema.validate(instance=load("sessions.json"), schema=load("schemas/sessions.schema.json"))


def test_projects_schema_rejects_missing_required_field():
    schema = load("schemas/projects.schema.json")
    bad = {"projects": [{"lab": "x", "incoming_dandiset_id": "000001"}]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_projects_schema_rejects_non_six_digit_id():
    schema = load("schemas/projects.schema.json")
    bad = load("projects.json")
    bad["projects"][0]["incoming_dandiset_id"] = "123"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_projects_schema_rejects_metadata_key_shadowing_a_reserved_placeholder():
    schema = load("schemas/projects.schema.json")
    bad = load("projects.json")
    bad["projects"][0]["metadata"] = {"incoming_dir": "nope"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_sessions_schema_rejects_empty_include():
    schema = load("schemas/sessions.schema.json")
    bad = {"labs": {"test-lab": {"include": []}}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_sessions_schema_rejects_unknown_property():
    schema = load("schemas/sessions.schema.json")
    bad = {"labs": {"test-lab": {"include": ["raw/*"], "typo_field": True}}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)
