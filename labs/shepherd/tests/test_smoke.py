"""Environment smoke test for the ported Shepherd converter.

The conversion code under ``labs/shepherd/code/`` is a verbatim port and is not
exercised end-to-end yet. What this suite checks is that the environment the
converter needs is actually present in whatever runtime it is installed into:
every third-party import resolves, the CLI parses, and FFmpeg is on PATH. That
is what gates the published container image, and it needs no fixtures and no
change to the ported code.

A real integration test belongs with the follow-up that fixes the converter.

Test functions take their arguments positionally by pytest's injection rules,
so the repository's keyword-only and positional-only conventions do not apply
to them.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parent.parent / "code" / "shepherd_to_nwb.py"


@pytest.fixture(scope="module")
def cli_help():
    """Importing the converter is slow, so `--help` runs once for the module."""
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
    )

    return completed


@pytest.mark.ai_generated
def test_ffprobe_on_path():
    """The converter shells out to ffprobe for video duration and frame count."""
    ffprobe_path = shutil.which("ffprobe")

    assert (ffprobe_path is not None) is True


@pytest.mark.ai_generated
def test_cli_help_exits_cleanly(cli_help):
    """A zero exit means every module-level import in the converter resolved."""
    assert cli_help.returncode == 0, cli_help.stderr


@pytest.mark.ai_generated
@pytest.mark.parametrize(
    "expected_flag",
    ["--input_folder", "--subject", "--session", "--config", "--out"],
)
def test_cli_help_advertises_flag(cli_help, expected_flag):
    assert (expected_flag in cli_help.stdout) is True
