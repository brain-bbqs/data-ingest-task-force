import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dispatch/

import record_run  # noqa: E402

pytestmark = pytest.mark.ai_generated


def test_manifest_lists_new_and_changed_files_but_not_untouched_or_hidden_ones(tmp_path, monkeypatch):
    root = tmp_path / "out"
    root.mkdir()
    (root / "untouched.nwb").write_text("same")
    (root / "changed.nwb").write_text("old")
    (root / "gone.nwb").write_text("bye")
    script = (
        "import pathlib, os; r = pathlib.Path(os.environ['ROOT']); "
        "(r / 'changed.nwb').write_text('newer'); (r / 'sub').mkdir(); (r / 'sub' / 'new.nwb').write_text('x'); "
        "(r / '.ingest_state.json').write_text('{}'); (r / 'gone.nwb').unlink()"
    )
    manifest_path = tmp_path / "record" / "manifest.json"
    monkeypatch.setenv("ROOT", str(root))
    exit_code = record_run.main(
        [
            "--cwd",
            str(tmp_path),
            "--root",
            str(root),
            "--manifest",
            str(manifest_path),
            "--",
            sys.executable,
            "-c",
            script,
        ]
    )

    assert exit_code == 0
    manifest = json.loads(manifest_path.read_text())
    assert [entry["path"] for entry in manifest["written"]] == ["changed.nwb", str(Path("sub") / "new.nwb")]
    assert manifest["written"][0]["size"] == 5
    assert manifest["removed"] == ["gone.nwb"]
    assert manifest["exit_code"] == 0


def test_manifest_is_written_and_exit_code_kept_when_the_command_fails(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    exit_code = record_run.main(
        ["--cwd", str(tmp_path), "--root", str(tmp_path / "missing"), "--manifest", str(manifest_path), "--"]
        + [sys.executable, "-c", "raise SystemExit(4)"]
    )
    assert exit_code == 4
    assert json.loads(manifest_path.read_text())["exit_code"] == 4
