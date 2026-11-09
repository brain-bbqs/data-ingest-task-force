"""Regenerate the synthetic manifest fixture and its semantic NWB summary.

Run from the repo root with python -m labs.sanes.tests.generate_fixtures.
No real animal metadata or lab media is included.
"""

import json
import shutil
import tempfile
from pathlib import Path

from . import synthetic
from .nwb_summary import summarize
from ..code import _sanes_to_nwb as converter

ROOT = Path(__file__).resolve().parent


def main():
    incoming = ROOT / "example_raw" / "big_arena"
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary)
        session = synthetic.write_sync_session(root=staging / "incoming")
        shutil.rmtree(incoming / session.name, ignore_errors=True)
        shutil.copytree(session, incoming / session.name)
        path = converter.build_nwb(
            session_dir=session,
            output_dir=staging / "output",
            config_path=ROOT.parent / "code" / "config_big_arena_2024_12.yaml",
        )
        expected = ROOT / "expected_output" / "big_arena.json"
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.write_text(json.dumps(summarize(path), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
