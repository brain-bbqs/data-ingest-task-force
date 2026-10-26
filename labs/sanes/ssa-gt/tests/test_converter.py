import importlib.util
from pathlib import Path

import pytest

module_path = Path(__file__).parents[1] / "code" / "_sanes_ssa_gt_to_nwb.py"
spec = importlib.util.spec_from_file_location("ssa_gt_converter", module_path)
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


@pytest.mark.ai_generated
@pytest.mark.parametrize(("value", "expected"), [("experiment_280", "experiment280"), ("track 1", "track1"), ("", "")])
def test_sanitize_label(value, expected):
    actual = converter.sanitize_label(value)
    assert actual == expected
