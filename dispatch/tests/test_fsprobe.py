import logging
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dispatch/

import fsprobe  # noqa: E402

pytestmark = pytest.mark.ai_generated


def truncate_stat_mtime(monkeypatch, granularity_seconds: float) -> None:
    """Make os.stat report mtimes rounded down to *granularity_seconds*, the
    way a filesystem that cannot store the sub-second part would."""
    original_stat = os.stat

    class TruncatedStat:
        def __init__(self, wrapped):
            self.st_mtime = (wrapped.st_mtime // granularity_seconds) * granularity_seconds

    monkeypatch.setattr(fsprobe.os, "stat", lambda path: TruncatedStat(original_stat(path)))


def test_probe_reports_no_error_on_a_filesystem_that_keeps_sub_second_mtimes(tmp_path):
    # tmp_path is ext4 or tmpfs under CI, both nanosecond-resolution.
    assert fsprobe.mtime_granularity_seconds(tmp_path) == 0.0


def test_probe_returns_none_when_it_cannot_write(tmp_path):
    assert fsprobe.mtime_granularity_seconds(tmp_path / "does-not-exist") is None


def test_probe_leaves_no_file_behind(tmp_path):
    fsprobe.mtime_granularity_seconds(tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "granularity_seconds",
    [
        pytest.param(1.0, id="whole-second-mtimes"),
        pytest.param(2.0, id="fat-exfat-two-second-mtimes"),
    ],
)
def test_probe_measures_how_much_precision_a_coarse_filesystem_loses(tmp_path, monkeypatch, granularity_seconds):
    truncate_stat_mtime(monkeypatch, granularity_seconds)
    expected = fsprobe._PROBE_MTIME - (fsprobe._PROBE_MTIME // granularity_seconds) * granularity_seconds
    assert fsprobe.mtime_granularity_seconds(tmp_path) == pytest.approx(expected)


def test_refresh_is_usable_on_a_precise_filesystem(tmp_path):
    assert fsprobe.warn_if_refresh_cannot_skip(tmp_path) is True


def test_refresh_is_usable_when_the_probe_could_not_run(tmp_path, monkeypatch):
    # Unknown is not a reason to claim the filesystem is broken.
    monkeypatch.setattr(fsprobe, "mtime_granularity_seconds", lambda directory: None)
    assert fsprobe.warn_if_refresh_cannot_skip(tmp_path) is True


@pytest.mark.parametrize(
    "error_seconds",
    [
        pytest.param(1e-3, id="millisecond-mtimes"),
        pytest.param(0.651, id="truncated-to-the-second"),
        pytest.param(2.0, id="fat-exfat"),
    ],
)
def test_coarse_filesystem_is_reported_as_unable_to_skip(tmp_path, monkeypatch, caplog, error_seconds):
    """The failure this module exists to name: a filesystem that truncates
    mtimes defeats dandi's refresh check on every asset, every pass."""
    monkeypatch.setattr(fsprobe, "mtime_granularity_seconds", lambda directory: error_seconds)
    with caplog.at_level(logging.WARNING, logger="dispatch"):
        usable = fsprobe.warn_if_refresh_cannot_skip(tmp_path)
    assert usable is False
    assert "re-downloaded on every pass" in caplog.text


def test_a_filesystem_inside_the_tolerance_is_not_warned_about(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(fsprobe, "mtime_granularity_seconds", lambda directory: 1e-7)
    with caplog.at_level(logging.WARNING, logger="dispatch"):
        usable = fsprobe.warn_if_refresh_cannot_skip(tmp_path)
    assert usable is True
    assert caplog.text == ""


def test_dandi_refresh_tolerance_matches_the_value_dandi_uses():
    """dandi.utils.is_same_time's default. If dandi ever loosens it, this
    module's warning threshold is wrong and should follow."""
    assert fsprobe.DANDI_REFRESH_TOLERANCE_SECONDS == 1e-6
