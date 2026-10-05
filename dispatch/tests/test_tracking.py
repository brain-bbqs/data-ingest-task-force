import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dispatch/

import tracking  # noqa: E402

pytestmark = pytest.mark.ai_generated

IMAGE = "ghcr.io/org/lab-ingest:latest"
PINNED = "docker://ghcr.io/org/lab-ingest@sha256:new"


def write_config(root: Path, *, updateurl: str | None) -> None:
    config = root / ".datalad" / "config"
    config.parent.mkdir(parents=True)
    lines = ['[datalad "dataset"]', "\tid = 1234", '[datalad "containers.lab-ingest"]', "\timage = envs/lab-ingest.sif"]
    if updateurl is not None:
        lines.append(f"\tupdateurl = {updateurl}")
    lines.append('\tcmdexec = "duct apptainer exec {img} {cmd}"')
    config.write_text("\n".join(lines) + "\n")


def test_read_container_config_parses_container_sections(tmp_path):
    write_config(tmp_path, updateurl=PINNED)
    config = tracking.read_container_config(tmp_path / ".datalad" / "config")
    assert config == {
        "lab-ingest": {
            "image": "envs/lab-ingest.sif",
            "updateurl": PINNED,
            "cmdexec": "duct apptainer exec {img} {cmd}",
        }
    }


@pytest.fixture
def calls(monkeypatch):
    recorded = []
    monkeypatch.setattr(tracking.subprocess, "run", lambda cmd, **kwargs: recorded.append(cmd))
    monkeypatch.setattr(tracking, "resolve_digest", lambda image, /: PINNED)
    return recorded


def test_image_is_left_alone_when_its_digest_has_not_moved(tmp_path, calls):
    write_config(tmp_path, updateurl=PINNED)
    (tmp_path / "envs").mkdir()
    (tmp_path / "envs" / "lab-ingest.sif").write_text("sif")

    tracked = tracking.TrackingDataset(root=tmp_path).image(image=IMAGE, dry_run=False)

    assert calls == []
    assert tracked == tracking.TrackedImage(name="lab-ingest", path=tmp_path / "envs" / "lab-ingest.sif", url=PINNED)


@pytest.mark.parametrize(
    ("updateurl", "sif_present", "expect_update_flag"),
    [
        ("docker://ghcr.io/org/lab-ingest@sha256:old", True, True),  # tag moved
        (PINNED, False, True),  # fresh clone: configured, but no local image
        (None, False, False),  # never added
    ],
)
def test_image_is_rebuilt_when_moved_or_missing(tmp_path, calls, updateurl, sif_present, expect_update_flag):
    """The old image is unstaged before an update re-adds it (see TrackingDataset.image)."""
    if updateurl is None:
        (tmp_path / ".datalad").mkdir()
        (tmp_path / ".datalad" / "config").write_text('[datalad "dataset"]\n\tid = 1234\n')
    else:
        write_config(tmp_path, updateurl=updateurl)
    if sif_present:
        (tmp_path / "envs").mkdir()
        (tmp_path / "envs" / "lab-ingest.sif").write_text("sif")

    tracking.TrackingDataset(root=tmp_path).image(image=IMAGE, dry_run=False)

    config_cmd, *unstage_cmds, add_cmd = calls
    assert unstage_cmds == ([["git", "rm", "-q", "--", "envs/lab-ingest.sif"]] if sif_present else [])
    assert config_cmd[-2:] == ["datalad.containers.lab-ingest.updateurl", PINNED]
    assert add_cmd[:5] == ["datalad", "containers-add", "lab-ingest", "--url", PINNED]
    assert add_cmd[add_cmd.index("--call-fmt") + 1] == tracking.CALL_FORMAT
    assert ("--update" in add_cmd) == expect_update_flag


def test_image_is_resolved_once_per_run(tmp_path, calls, monkeypatch):
    resolved = []
    monkeypatch.setattr(tracking, "resolve_digest", lambda image, /: resolved.append(image) or PINNED)
    dataset = tracking.TrackingDataset(root=tmp_path)
    dataset.image(image=IMAGE, dry_run=False)
    dataset.image(image=IMAGE, dry_run=False)
    assert resolved == [IMAGE]
