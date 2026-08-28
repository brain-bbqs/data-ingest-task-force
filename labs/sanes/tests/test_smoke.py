"""Environment smoke test for the ported Sanes converter.

The conversion code under ``labs/sanes/code/`` is a port of the original
notebook and is not exercised end-to-end yet (see ``labs/sanes/README.md``).
What this suite checks is that the environment the converter needs is actually
present in whatever runtime it is installed into: every third-party import
resolves, the CLI parses, and FFmpeg is on PATH. That is what gates the
published container image, and it needs no fixtures.

A real integration test belongs with the follow-up that takes ownership of the
port, since it needs real example data (audio chunks, videos, SLEAP files and
annotations) that this repository does not have yet.

Test functions take their arguments positionally by pytest's injection rules,
so the repository's keyword-only and positional-only conventions do not apply
to them.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CODE = Path(__file__).resolve().parent.parent / "code"
CONVERTER = CODE / "_sanes_to_nwb.py"
BATCH = CODE / "batch_convert.py"


@pytest.fixture(scope="module")
def converter_help():
    """Importing the converter is slow, so `--help` runs once for the module."""
    completed = subprocess.run(
        [sys.executable, str(CONVERTER), "--help"],
        capture_output=True,
        text=True,
    )

    return completed


@pytest.fixture(scope="module")
def batch_help():
    completed = subprocess.run(
        [sys.executable, str(BATCH), "--help"],
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
@pytest.mark.parametrize("help_fixture", ["converter_help", "batch_help"])
def test_cli_help_exits_cleanly(request, help_fixture):
    """A zero exit means every module-level import in the script resolved."""
    completed = request.getfixturevalue(help_fixture)

    assert completed.returncode == 0, completed.stderr


@pytest.mark.ai_generated
@pytest.mark.parametrize("expected_flag", ["--input", "--out", "--config"])
def test_converter_help_advertises_flag(converter_help, expected_flag):
    assert (expected_flag in converter_help.stdout) is True


@pytest.mark.ai_generated
@pytest.mark.parametrize("expected_flag", ["--input", "--output", "--config", "--overwrite"])
def test_batch_help_advertises_flag(batch_help, expected_flag):
    assert (expected_flag in batch_help.stdout) is True
