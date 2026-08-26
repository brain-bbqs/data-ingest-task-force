"""Measures how precisely a filesystem stores modification times.

This exists for one reason: ``dandi download -e refresh`` decides whether an
asset already on disk can be skipped by comparing the local file's mtime
against the timestamp in the asset record, and it demands they agree to
within one microsecond (``dandi.utils.is_same_time``, default
``tolerance=1e-6``). dandi sets that mtime itself, right after downloading,
with ``os.utime(path, (time.time(), mtime.timestamp()))``.

So the comparison only ever succeeds if the filesystem stores the sub-second
part of what ``os.utime`` was given. On ext4 or XFS (nanosecond mtimes) it
round-trips exactly. On a filesystem that truncates mtimes to whole seconds,
the value read back differs from the record by up to a full second, which is
six orders of magnitude past the tolerance. Every asset then looks stale on
every pass, and refresh re-downloads the entire dandiset forever.

That failure is invisible from the outside: the run still succeeds, it just
transfers everything again. Probing the target directory turns it into one
line in the log.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger("dispatch")

# dandi.utils.is_same_time's default tolerance, which dandi.download's
# refresh check relies on.
DANDI_REFRESH_TOLERANCE_SECONDS = 1e-6

# Chosen so truncation shows up in every field a filesystem might drop:
# whole seconds, milliseconds, and microseconds.
_PROBE_MTIME = 1_234_567_890.123456


def mtime_granularity_seconds(directory: Path, /) -> float | None:
    """Round-trip error when storing a sub-second mtime in *directory*.

    Returns the absolute difference, in seconds, between an mtime written
    with ``os.utime`` and the one read back by ``os.stat`` -- 0.0 on a
    filesystem that preserves it exactly. Returns None if the probe could not
    run at all (directory missing, read-only, out of space), since that is a
    reason to stay quiet rather than to report a filesystem problem.
    """
    try:
        handle, probe_path = tempfile.mkstemp(dir=directory, prefix=".mtime-probe.")
    except OSError as error:
        log.debug("could not create an mtime probe file in %s: %s", directory, error)
        return None
    try:
        os.close(handle)
        os.utime(probe_path, (_PROBE_MTIME, _PROBE_MTIME))
        observed = os.stat(probe_path).st_mtime
    except OSError as error:
        log.debug("could not probe mtime precision in %s: %s", directory, error)
        return None
    finally:
        Path(probe_path).unlink(missing_ok=True)
    error_seconds = abs(observed - _PROBE_MTIME)
    return error_seconds


def warn_if_refresh_cannot_skip(directory: Path, /) -> bool:
    """Log whether *directory* can support ``dandi download -e refresh``.

    Returns True when refresh's mtime comparison is workable there. A False
    result means every refresh pass will re-download every asset, which is
    worth saying out loud in a cron log that would otherwise just look slow.
    """
    error_seconds = mtime_granularity_seconds(directory)
    if error_seconds is None:
        return True
    if error_seconds <= DANDI_REFRESH_TOLERANCE_SECONDS:
        log.debug("%s preserves sub-second mtimes (error %.1e s), refresh can skip unchanged assets", directory, error_seconds)
        return True
    log.warning(
        "%s loses %.6f s of mtime precision, more than the %.0e s `dandi download -e refresh` allows; "
        "every asset will look stale and be re-downloaded on every pass. Point --incoming-root at a "
        "filesystem with sub-second mtimes (ext4/XFS rather than a mounted Windows/FAT/exFAT volume).",
        directory,
        error_seconds,
        DANDI_REFRESH_TOLERANCE_SECONDS,
    )
    return False
