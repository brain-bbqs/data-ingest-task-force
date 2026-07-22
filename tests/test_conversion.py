#!/usr/bin/env python3
"""Integration test for ``code/convert_raw_to_bids.py``.

Runs the actual conversion script on the committed mock input tree
(``tests/example_raw/``) and asserts the produced BIDS dataset matches the
committed golden tree (``tests/expected_output/``) exactly — mirroring the
``example_logs`` -> ``expected_output`` fixture pattern used in
``dandi/s3-log-extraction``.

``ffprobe`` is provided by the PyAV-backed ``tests/ffprobe_shim.py`` so the run
is deterministic and needs no system FFmpeg install. To (re)generate the
fixtures after an intentional change, run ``python3 tests/generate_fixtures.py``.

Run with::

    python3 -m pytest tests/ -q
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
sys.path.insert(0, str(REPO / "code"))

import convert_raw_to_bids as conv  # noqa: E402

EXAMPLE_RAW = TESTS / "example_raw"
EXPECTED_OUTPUT = TESTS / "expected_output"
SHIM = TESTS / "ffprobe_shim.py"


def _relative_files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def _assert_file_matches(rel: str, produced: Path, expected: Path) -> None:
    prod, exp = produced / rel, expected / rel
    if rel.endswith(".json"):
        # Compare semantically so key order / whitespace never causes churn.
        assert json.loads(prod.read_text()) == json.loads(exp.read_text()), \
            f"JSON mismatch: {rel}"
    elif rel.endswith((".tsv", ".txt")) or Path(rel).name == "README":
        assert prod.read_text() == exp.read_text(), f"text mismatch: {rel}"
    else:
        # Media files are copied verbatim, so bytes must be identical.
        assert prod.read_bytes() == exp.read_bytes(), f"binary mismatch: {rel}"


def test_conversion_matches_expected_output(tmp_path):
    assert EXAMPLE_RAW.is_dir(), "run tests/generate_fixtures.py first"
    assert EXPECTED_OUTPUT.is_dir(), "run tests/generate_fixtures.py first"

    SHIM.chmod(SHIM.stat().st_mode | stat.S_IEXEC | stat.S_IRUSR)
    out = tmp_path / "rawbids"

    exit_code = conv.Converter(
        raw_dir=EXAMPLE_RAW,
        bids_dir=out,
        ffprobe_bin=str(SHIM),
        species="Ovis aries",
        authors=["Kemere Lab"],
    ).run()
    assert exit_code == 0

    produced_files = _relative_files(out)
    expected_files = _relative_files(EXPECTED_OUTPUT)
    assert produced_files == expected_files, (
        "file set differs\n"
        f"  only produced: {sorted(produced_files - expected_files)}\n"
        f"  only expected: {sorted(expected_files - produced_files)}"
    )

    for rel in sorted(expected_files):
        _assert_file_matches(rel, out, EXPECTED_OUTPUT)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
