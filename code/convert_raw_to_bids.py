#!/usr/bin/env python3
"""Convert Kemere-lab raw behavioral recordings into a BEP047 BIDS dataset.

This script reorganizes a ``sourcedata/raw`` tree of behavioral video/image
recordings into a standardized BIDS dataset under ``sourcedata/rawbids``,
following BEP047 (audio/video/image recordings in the ``beh`` datatype).

The raw tree is expected to look like::

    <raw>/
      <MMDDYYYY>-Session<N>/         # one session per directory
        <camera>/                     # e.g. "overhead"  -> recording-<camera>
          beh/
            <name>.mp4                # -> _video (or _audiovideo if audio present)
            <name>.settings           # merged into the video JSON sidecar
            <name>.png                # -> _image
            ...                       # notes.txt, *.srt, *.pv, ... are ignored

and is converted to::

    <bids>/
      dataset_description.json
      README
      participants.tsv / participants.json
      sub-multi/
        ses-<label>/
          sub-multi_ses-<label>_scans.tsv / .json
          beh/
            sub-multi_ses-<label>_recording-<camera>_video.mp4  (+ .json)
            sub-multi_ses-<label>_acq-<label>_recording-<camera>_image.png (+ .json)

Media metadata for the JSON sidecars is obtained with ``ffprobe`` (part of
FFmpeg). Only ``ffprobe`` is required at runtime; no Python packages beyond the
standard library are used.

References
----------
* BEP047 specification PR:
  https://github.com/bids-standard/bids-specification/pull/2231
* Example dataset:
  https://github.com/bids-standard/bids-examples (beh_audio_video_recordings)
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__version__ = "0.1.0"

# --------------------------------------------------------------------------- #
# Constants derived from the BEP047 schema
# --------------------------------------------------------------------------- #

DATATYPE = "beh"
# BEP047 targets this BIDS version in the reference example dataset.
BIDS_VERSION = "1.10.0"

# extension -> media kind, per src/schema/rules/files/raw/beh.yaml
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}  # ".jpeg" is normalized to ".jpg"
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".ogg"}

# Canonical BIDS entity order (subset relevant to the beh datatype), taken from
# the BIDS entity table. Only these entities are permitted on beh media files.
ENTITY_ORDER = ["sub", "ses", "task", "acq", "run", "recording", "split"]

# Sidecar key namespacing the raw ``*.settings`` provenance metadata.
SETTINGS_SIDECAR_KEY = "TrackingSettings"

# pixel-format -> bits per channel, used when ffprobe does not report
# ``bits_per_raw_sample`` directly.
_PIXFMT_BIT_DEPTH = {
    "yuv420p": 8, "yuvj420p": 8, "yuv422p": 8, "yuvj422p": 8,
    "yuv444p": 8, "yuvj444p": 8, "nv12": 8, "nv21": 8,
    "rgb24": 8, "bgr24": 8, "gray": 8, "gray8": 8, "ya8": 8,
    "rgba": 8, "bgra": 8, "argb": 8, "abgr": 8, "pal8": 8, "gbrp": 8,
    "monob": 1, "monow": 1,
    "yuv420p10le": 10, "yuv422p10le": 10, "yuv444p10le": 10,
    "p010le": 10, "gray10le": 10, "gbrp10le": 10,
    "yuv420p12le": 12, "yuv422p12le": 12, "yuv444p12le": 12, "gray12le": 12,
    "yuv420p16le": 16, "gray16le": 16, "rgb48le": 16, "rgba64le": 16,
    "gbrp16le": 16,
}

# h.264 profile name -> profile_idc, for building RFC 6381 codec strings.
_H264_PROFILE_IDC = {
    "Constrained Baseline": 0x42, "Baseline": 0x42, "Main": 0x4D,
    "Extended": 0x58, "High": 0x64, "High 10": 0x6E, "High 4:2:2": 0x7A,
    "High 4:4:4": 0xF4, "High 4:4:4 Predictive": 0xF4,
}

# aac profile name -> RFC 6381 object type suffix.
_AAC_RFC6381 = {"LC": "mp4a.40.2", "HE-AAC": "mp4a.40.5", "HE-AACv2": "mp4a.40.29"}


# --------------------------------------------------------------------------- #
# Small typed helpers
# --------------------------------------------------------------------------- #

def _to_int(value: Any) -> int | None:
    """Best-effort integer coercion; returns None for missing/"N/A" values."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _to_float(value: Any) -> float | None:
    """Best-effort float coercion; returns None for missing/"N/A" values."""
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


def sanitize_label(text: str) -> str:
    """Reduce ``text`` to a BIDS-valid label (alphanumeric characters only)."""
    return re.sub(r"[^0-9A-Za-z]", "", text)


# --------------------------------------------------------------------------- #
# .settings parsing
# --------------------------------------------------------------------------- #

def _coerce_setting_value(raw: str) -> Any:
    """Coerce a raw ``*.settings`` value string to a JSON-friendly Python type.

    Handles booleans, integers, floats, quoted strings, and bracketed lists
    (for example ``[[10,100000]]``). Barewords such as
    ``background_subtraction`` are kept as strings.
    """
    text = raw.strip()
    if text == "":
        return ""
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        # Handles ints, floats, quoted strings and Python-literal lists.
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text  # bareword string, e.g. "background_subtraction"


def parse_settings(text: str) -> dict[str, Any]:
    """Parse the ``key = value`` body of a ``*.settings`` file.

    Blank lines and ``#`` comments are ignored. Values are coerced to native
    types via :func:`_coerce_setting_value`.
    """
    parsed: dict[str, Any] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key:
            continue
        # Drop trailing inline comments only when they are clearly separated and
        # not inside a quoted string / list. Keep it conservative: strip a
        # trailing " # ..." comment only when no quote/bracket precedes it.
        parsed[key] = _coerce_setting_value(value)
    return parsed


def build_settings_block(settings_path: Path) -> dict[str, Any]:
    """Read a ``*.settings`` file and wrap it as a provenance sidecar block."""
    text = settings_path.read_text(encoding="utf-8", errors="replace")
    return {
        "Description": (
            "Raw parameters from the Kemere-lab tracking / video-conversion "
            "pipeline, preserved verbatim from the source `*.settings` file "
            "for provenance. Not part of the BIDS specification."
        ),
        "SourceFile": settings_path.name,
        "Parameters": parse_settings(text),
    }


# --------------------------------------------------------------------------- #
# Session-label derivation
# --------------------------------------------------------------------------- #

@dataclass
class SessionInfo:
    label: str
    iso_date: str | None  # "YYYY-MM-DD" when parseable, else None
    source_name: str
    session_index: int | None


_SESSION_RE = re.compile(
    r"^(?P<mm>\d{2})(?P<dd>\d{2})(?P<yyyy>\d{4})"
    r"[-_ ]*[Ss]ession[-_ ]*(?P<idx>\d+)$"
)


def derive_session_label(folder_name: str) -> SessionInfo:
    """Derive a BIDS session label from a raw session-folder name.

    ``<MMDDYYYY>-Session<N>`` -> ISO-date label ``YYYYMMDD`` (with an ``sNN``
    suffix for the 2nd and later sessions on the same day). Anything that does
    not match falls back to an alphanumeric sanitization of the folder name.
    """
    match = _SESSION_RE.match(folder_name.strip())
    if match:
        iso_compact = f"{match['yyyy']}{match['mm']}{match['dd']}"
        idx = int(match["idx"])
        label = iso_compact if idx <= 1 else f"{iso_compact}s{idx:02d}"
        iso_date = f"{match['yyyy']}-{match['mm']}-{match['dd']}"
        return SessionInfo(label, iso_date, folder_name, idx)
    fallback = sanitize_label(folder_name) or "unknown"
    return SessionInfo(fallback, None, folder_name, None)


# --------------------------------------------------------------------------- #
# ffprobe interface
# --------------------------------------------------------------------------- #

class FFprobeError(RuntimeError):
    pass


def run_ffprobe(path: Path, ffprobe_bin: str, count_frames: bool = False) -> dict:
    """Run ``ffprobe`` on ``path`` and return the parsed JSON document."""
    cmd = [
        ffprobe_bin, "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
    ]
    if count_frames:
        cmd += ["-count_frames"]
    cmd.append(str(path))
    try:
        completed = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
    except FileNotFoundError as exc:
        raise FFprobeError(
            f"ffprobe executable not found: {ffprobe_bin!r}. Install FFmpeg or "
            f"pass --ffprobe /path/to/ffprobe."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise FFprobeError(
            f"ffprobe failed for {path} (exit {exc.returncode}): "
            f"{exc.stderr.strip()}"
        ) from exc
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise FFprobeError(f"could not parse ffprobe JSON for {path}: {exc}") from exc


def parse_frame_rate(rate: str | None) -> float | None:
    """Convert an ffprobe frame-rate string (e.g. ``"30000/1001"``) to Hz."""
    if not rate:
        return None
    rate = str(rate).strip()
    if rate in ("0/0", "0", "N/A", ""):
        return None
    if "/" in rate:
        num, _, den = rate.partition("/")
        numerator = _to_float(num)
        denominator = _to_float(den)
        if numerator is None or not denominator:
            return None
        return numerator / denominator
    return _to_float(rate)


def _first_stream(probe: dict, codec_type: str) -> dict | None:
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == codec_type:
            return stream
    return None


def pix_fmt_bit_depth(pix_fmt: str | None, stream: dict) -> int | None:
    """Bits per channel for a video/image stream."""
    reported = _to_int(stream.get("bits_per_raw_sample"))
    if reported and reported > 0:
        return reported
    if pix_fmt:
        return _PIXFMT_BIT_DEPTH.get(pix_fmt)
    return None


def rfc6381_video(stream: dict) -> str | None:
    """Best-effort RFC 6381 codec string for a video stream (h.264 only)."""
    if stream.get("codec_name") != "h264":
        return None
    profile = stream.get("profile")
    level = _to_int(stream.get("level"))
    if profile not in _H264_PROFILE_IDC or not level or level <= 0:
        return None
    profile_idc = _H264_PROFILE_IDC[profile]
    constraints = 0x40 if profile == "Constrained Baseline" else 0x00
    tag = (stream.get("codec_tag_string") or "").strip()
    base = tag if tag in ("avc1", "avc3") else "avc1"
    # RFC 6381 codec strings use lowercase hexadecimal by convention.
    return f"{base}.{profile_idc:02x}{constraints:02x}{level:02x}"


def rfc6381_audio(stream: dict) -> str | None:
    """Best-effort RFC 6381 codec string for an audio stream (AAC only)."""
    if stream.get("codec_name") != "aac":
        return None
    profile = stream.get("profile")
    return _AAC_RFC6381.get(profile)


def format_creation_time(probe: dict) -> str | None:
    """Return the container ``creation_time`` tag normalized to ISO 8601."""
    tags = probe.get("format", {}).get("tags", {}) or {}
    creation = tags.get("creation_time")
    stream = _first_stream(probe, "video") or _first_stream(probe, "audio")
    if not creation and stream:
        creation = (stream.get("tags", {}) or {}).get("creation_time")
    if not creation:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", str(creation))
    if match:
        return f"{match.group(1)}T{match.group(2)}"
    date_only = re.match(r"(\d{4}-\d{2}-\d{2})", str(creation))
    if date_only:
        return f"{date_only.group(1)}T00:00:00"
    return None


def device_from_tags(probe: dict) -> str | None:
    """Extract a human-readable device description from container tags."""
    tags = {k.lower(): v for k, v in (probe.get("format", {}).get("tags", {}) or {}).items()}
    make = tags.get("make") or tags.get("com.apple.quicktime.make")
    model = tags.get("model") or tags.get("com.apple.quicktime.model")
    if make and model:
        return f"{make} {model}".strip()
    return model or make or None


# --------------------------------------------------------------------------- #
# Sidecar construction
# --------------------------------------------------------------------------- #

@dataclass
class MediaResult:
    suffix: str
    sidecar: dict[str, Any]


def build_media_sidecar(
    probe: dict,
    *,
    device_position: str | None,
    device_override: str | None,
    warnings: list[str],
    media_path: Path,
) -> MediaResult:
    """Build a JSON sidecar for a video / audiovideo file from ffprobe output."""
    sidecar: dict[str, Any] = {}
    video = _first_stream(probe, "video")
    audio = _first_stream(probe, "audio")
    if video is None:
        raise FFprobeError(f"no video stream found in {media_path}")

    # Duration (RecordingDuration, seconds).
    duration = _to_float(probe.get("format", {}).get("duration"))
    if duration is None:
        duration = _to_float(video.get("duration"))
    if duration is not None and duration > 0:
        sidecar["RecordingDuration"] = round(duration, 3)

    # Video stream properties.
    if video.get("codec_name"):
        sidecar["VideoCodec"] = video["codec_name"]
    frame_rate = parse_frame_rate(video.get("avg_frame_rate")) \
        or parse_frame_rate(video.get("r_frame_rate"))
    if frame_rate and frame_rate > 0:
        sidecar["VideoFrameRate"] = round(frame_rate, 6)

    frame_count = _to_int(video.get("nb_frames")) or _to_int(video.get("nb_read_frames"))
    if not frame_count and duration and frame_rate:
        frame_count = round(duration * frame_rate)
        warnings.append(
            f"{media_path.name}: VideoFrameCount not reported by ffprobe; "
            f"estimated as duration x frame rate ({frame_count})."
        )
    if frame_count and frame_count >= 1:
        sidecar["VideoFrameCount"] = int(frame_count)

    rfc = rfc6381_video(video)
    if rfc:
        sidecar["VideoCodecRFC6381"] = rfc

    width = _to_int(video.get("width"))
    height = _to_int(video.get("height"))
    if width:
        sidecar["ImageWidth"] = width
    if height:
        sidecar["ImageHeight"] = height
    if video.get("pix_fmt"):
        sidecar["ImagePixelFormat"] = video["pix_fmt"]
    bit_depth = pix_fmt_bit_depth(video.get("pix_fmt"), video)
    if bit_depth:
        sidecar["ImageBitDepth"] = bit_depth

    # Audio stream properties (only when an audio stream is present).
    suffix = "video"
    if audio is not None:
        suffix = "audiovideo"
        if audio.get("codec_name"):
            sidecar["AudioCodec"] = audio["codec_name"]
        sample_rate = _to_float(audio.get("sample_rate"))
        if sample_rate and sample_rate > 0:
            sidecar["AudioSampleRate"] = int(sample_rate) if sample_rate.is_integer() else sample_rate
        channels = _to_int(audio.get("channels"))
        if channels and channels >= 1:
            sidecar["AudioChannelCount"] = channels
        audio_bits = _to_int(audio.get("bits_per_raw_sample")) or _to_int(audio.get("bits_per_sample"))
        if audio_bits and audio_bits > 0:
            sidecar["AudioBitDepth"] = audio_bits
        audio_rfc = rfc6381_audio(audio)
        if audio_rfc:
            sidecar["AudioCodecRFC6381"] = audio_rfc

    # Device metadata (all optional).
    device = device_override or device_from_tags(probe)
    if device:
        sidecar["Device"] = device
    serial = (probe.get("format", {}).get("tags", {}) or {}).get("device_serial")
    if serial:
        sidecar["DeviceSerialNumber"] = str(serial)
    if device_position:
        sidecar["DevicePosition"] = device_position

    return MediaResult(suffix=suffix, sidecar=sidecar)


def build_image_sidecar(
    probe: dict,
    *,
    device_position: str | None,
    device_override: str | None,
) -> dict[str, Any]:
    """Build a JSON sidecar for a still image from ffprobe output."""
    sidecar: dict[str, Any] = {}
    stream = _first_stream(probe, "video")  # ffprobe models still images as a video stream
    if stream is None:
        return sidecar
    width = _to_int(stream.get("width"))
    height = _to_int(stream.get("height"))
    if width:
        sidecar["ImageWidth"] = width
    if height:
        sidecar["ImageHeight"] = height
    if stream.get("pix_fmt"):
        sidecar["ImagePixelFormat"] = stream["pix_fmt"]
    bit_depth = pix_fmt_bit_depth(stream.get("pix_fmt"), stream)
    if bit_depth:
        sidecar["ImageBitDepth"] = bit_depth
    device = device_override or device_from_tags(probe)
    if device:
        sidecar["Device"] = device
    if device_position:
        sidecar["DevicePosition"] = device_position
    return sidecar


# --------------------------------------------------------------------------- #
# Filename / entity handling
# --------------------------------------------------------------------------- #

def build_stem(entities: dict[str, str], suffix: str) -> str:
    """Build a BIDS filename stem from an entity dict and a suffix."""
    parts = [
        f"{key}-{entities[key]}"
        for key in ENTITY_ORDER
        if entities.get(key)
    ]
    parts.append(suffix)
    return "_".join(parts)


def recording_label_from_path(session_dir: Path, media_path: Path) -> str | None:
    """Derive the ``recording`` entity from the camera sub-directory.

    Path parts between the session directory and the file are used, dropping a
    ``beh``/``raw`` datatype folder, then alphanumeric-sanitized.
    """
    rel_parts = media_path.parent.relative_to(session_dir).parts
    meaningful = [p for p in rel_parts if p.lower() not in ("beh", "raw", "")]
    if not meaningful:
        return None
    label = sanitize_label("".join(meaningful))
    return label or None


def image_acq_label(stem: str, recording: str | None) -> str:
    """Derive an ``acq`` label for an image from its filename stem.

    The camera/recording token and generic words (``video``, ``image``) are
    dropped; the remaining tokens are lower-cased and concatenated. If nothing
    meaningful remains, the full sanitized stem is used as a fallback.
    """
    tokens = re.split(r"[_\-\s.]+", stem.lower())
    drop = {"video", "image", "img"}
    if recording:
        drop.add(recording.lower())
    kept = [t for t in tokens if t and t not in drop]
    label = sanitize_label("".join(kept))
    return label or sanitize_label(stem) or "still"


# --------------------------------------------------------------------------- #
# File placement
# --------------------------------------------------------------------------- #

def place_file(src: Path, dst: Path, mode: str, dry_run: bool) -> None:
    """Copy/symlink/hardlink/move ``src`` to ``dst`` according to ``mode``."""
    if dry_run:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if mode == "copy":
        shutil.copy2(src, dst)
    elif mode == "symlink":
        dst.symlink_to(src.resolve())
    elif mode == "hardlink":
        try:
            dst.hardlink_to(src)
        except OSError:
            shutil.copy2(src, dst)
    elif mode == "move":
        shutil.move(str(src), str(dst))
    else:  # pragma: no cover - guarded by argparse choices
        raise ValueError(f"unknown link mode: {mode}")


def write_json(path: Path, data: dict, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def write_text(path: Path, text: str, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Conversion driver
# --------------------------------------------------------------------------- #

@dataclass
class Converter:
    raw_dir: Path
    bids_dir: Path
    subject: str = "multi"
    link_mode: str = "copy"
    ffprobe_bin: str = "ffprobe"
    count_frames: bool = False
    skip_metadata: bool = False
    device: str | None = None
    species: str = "n/a"
    dataset_name: str = "Kemere lab behavioral recordings"
    authors: list[str] = field(default_factory=lambda: ["Kemere Lab"])
    overwrite: bool = False
    dry_run: bool = False
    verbose: bool = False

    warnings: list[str] = field(default_factory=list)
    scans: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    converted: int = 0
    skipped_files: list[Path] = field(default_factory=list)
    # Filename-uniqueness sets keyed by session label, so distinct raw folders
    # that resolve to the same session label cannot clobber one another.
    _used_by_label: dict[str, set] = field(default_factory=dict)

    # -- logging ----------------------------------------------------------- #
    def log(self, message: str) -> None:
        print(message)

    def vlog(self, message: str) -> None:
        if self.verbose:
            print(message)

    # -- ffprobe (with skip-metadata escape hatch) ------------------------- #
    def probe(self, path: Path) -> dict | None:
        if self.skip_metadata:
            return None
        return run_ffprobe(path, self.ffprobe_bin, count_frames=self.count_frames)

    # -- discovery --------------------------------------------------------- #
    def session_dirs(self) -> list[Path]:
        return sorted(p for p in self.raw_dir.iterdir() if p.is_dir())

    def media_files(self, session_dir: Path) -> list[Path]:
        files = []
        for path in sorted(session_dir.rglob("*")):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            if ext in VIDEO_EXTENSIONS or ext in IMAGE_EXTENSIONS or ext in AUDIO_EXTENSIONS:
                files.append(path)
        return files

    # -- per-file conversion ---------------------------------------------- #
    def convert_session(self, session_dir: Path) -> None:
        info = derive_session_label(session_dir.name)
        ses_label = info.label
        beh_dir = self.bids_dir / f"sub-{self.subject}" / f"ses-{ses_label}" / DATATYPE
        self.scans.setdefault(ses_label, [])
        used_stems = self._used_by_label.setdefault(ses_label, set())

        self.log(f"Session {session_dir.name!r} -> ses-{ses_label}")

        for media_path in self.media_files(session_dir):
            ext = media_path.suffix.lower()
            recording = recording_label_from_path(session_dir, media_path)
            device_position = recording  # camera mounting position, e.g. "overhead"

            if ext in VIDEO_EXTENSIONS:
                self._convert_video(
                    media_path, info, beh_dir, recording, device_position, used_stems
                )
            elif ext in IMAGE_EXTENSIONS:
                self._convert_image(
                    media_path, info, beh_dir, recording, device_position, used_stems
                )
            elif ext in AUDIO_EXTENSIONS:
                self._convert_audio(
                    media_path, info, beh_dir, recording, device_position, used_stems
                )

        # Record ignored, non-media files for the summary.
        for path in sorted(session_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() not in (
                VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | {".settings"}
            ):
                self.skipped_files.append(path)

    def _unique_stem(self, entities: dict, suffix: str, used: set[str],
                     disambiguator: str) -> str:
        """Build a filename stem that is unique within the session.

        On collision, an ``acq`` entity derived from the source filename is
        added (then numerically bumped) so no two outputs share a name.
        """
        stem = build_stem(entities, suffix)
        if stem not in used:
            used.add(stem)
            return stem
        working = dict(entities)
        if not working.get("acq"):
            working["acq"] = disambiguator
            stem = build_stem(working, suffix)
            if stem not in used:
                used.add(stem)
                return stem
        base_acq = working.get("acq") or disambiguator
        index = 2
        while True:
            working["acq"] = f"{base_acq}{index}"
            candidate = build_stem(working, suffix)
            if candidate not in used:
                used.add(candidate)
                return candidate
            index += 1

    def _target_ext(self, ext: str) -> str:
        return ".jpg" if ext == ".jpeg" else ext

    def _convert_video(self, media_path, info, beh_dir, recording, device_position, used):
        probe = self.probe(media_path)
        entities = {"sub": self.subject, "ses": info.label}
        if recording:
            entities["recording"] = recording

        settings_block = self._settings_for(media_path)
        if probe is not None:
            result = build_media_sidecar(
                probe,
                device_position=device_position,
                device_override=self.device,
                warnings=self.warnings,
                media_path=media_path,
            )
            suffix, sidecar = result.suffix, result.sidecar
            acq_time = format_creation_time(probe)
        else:
            suffix, sidecar = "video", {}
            if device_position:
                sidecar["DevicePosition"] = device_position
            acq_time = None
        if settings_block:
            sidecar[SETTINGS_SIDECAR_KEY] = settings_block

        disambiguator = image_acq_label(media_path.stem, recording)
        stem = self._unique_stem(entities, suffix, used, disambiguator)
        self._emit(media_path, beh_dir, stem, media_path.suffix.lower(),
                   sidecar, info, acq_time)

    def _convert_audio(self, media_path, info, beh_dir, recording, device_position, used):
        probe = self.probe(media_path)
        entities = {"sub": self.subject, "ses": info.label}
        if recording:
            entities["recording"] = recording
        sidecar: dict[str, Any] = {}
        acq_time = None
        if probe is not None:
            audio = _first_stream(probe, "audio")
            duration = _to_float(probe.get("format", {}).get("duration"))
            if duration and duration > 0:
                sidecar["RecordingDuration"] = round(duration, 3)
            if audio:
                if audio.get("codec_name"):
                    sidecar["AudioCodec"] = audio["codec_name"]
                sample_rate = _to_float(audio.get("sample_rate"))
                if sample_rate and sample_rate > 0:
                    sidecar["AudioSampleRate"] = int(sample_rate) if sample_rate.is_integer() else sample_rate
                channels = _to_int(audio.get("channels"))
                if channels:
                    sidecar["AudioChannelCount"] = channels
                bits = _to_int(audio.get("bits_per_raw_sample")) or _to_int(audio.get("bits_per_sample"))
                if bits and bits > 0:
                    sidecar["AudioBitDepth"] = bits
                rfc = rfc6381_audio(audio)
                if rfc:
                    sidecar["AudioCodecRFC6381"] = rfc
            acq_time = format_creation_time(probe)
        settings_block = self._settings_for(media_path)
        if settings_block:
            sidecar[SETTINGS_SIDECAR_KEY] = settings_block
        disambiguator = image_acq_label(media_path.stem, recording)
        stem = self._unique_stem(entities, "audio", used, disambiguator)
        self._emit(media_path, beh_dir, stem, media_path.suffix.lower(),
                   sidecar, info, acq_time)

    def _convert_image(self, media_path, info, beh_dir, recording, device_position, used):
        probe = self.probe(media_path)
        acq = image_acq_label(media_path.stem, recording)
        entities = {"sub": self.subject, "ses": info.label, "acq": acq}
        if recording:
            entities["recording"] = recording
        stem = self._unique_stem(entities, "image", used, acq)

        if probe is not None:
            sidecar = build_image_sidecar(
                probe, device_position=device_position, device_override=self.device
            )
            acq_time = format_creation_time(probe)
        else:
            sidecar = {}
            if device_position:
                sidecar["DevicePosition"] = device_position
            acq_time = None
        settings_block = self._settings_for(media_path)
        if settings_block:
            sidecar[SETTINGS_SIDECAR_KEY] = settings_block

        target_ext = self._target_ext(media_path.suffix.lower())
        self._emit(media_path, beh_dir, stem, target_ext, sidecar, info, acq_time)

    def _settings_for(self, media_path: Path) -> dict | None:
        settings_path = media_path.with_suffix(".settings")
        if settings_path.is_file():
            return build_settings_block(settings_path)
        return None

    def _emit(self, src, beh_dir, stem, ext, sidecar, info, acq_time):
        dst = beh_dir / f"{stem}{ext}"
        json_dst = beh_dir / f"{stem}.json"
        if dst.exists() and not self.overwrite:
            self.warnings.append(f"exists, skipped (use --overwrite): {dst}")
            return
        place_file(src, dst, self.link_mode, self.dry_run)
        write_json(json_dst, sidecar, self.dry_run)
        self.converted += 1
        self.vlog(f"  {src.relative_to(self.raw_dir)}  ->  {dst.relative_to(self.bids_dir)}")

        # scans entry: participant-relative path (includes ses-<label>/).
        rel = dst.relative_to(self.bids_dir / f"sub-{self.subject}").as_posix()
        when = acq_time or (f"{info.iso_date}T00:00:00" if info.iso_date else "n/a")
        self.scans[info.label].append((rel, when))

    # -- dataset-level files ---------------------------------------------- #
    def write_dataset_files(self) -> None:
        desc = {
            "Name": self.dataset_name,
            "BIDSVersion": BIDS_VERSION,
            "DatasetType": "raw",
            "Authors": self.authors,
            "GeneratedBy": [
                {
                    "Name": "convert_raw_to_bids.py",
                    "Version": __version__,
                    "Description": (
                        "Reorganizes raw behavioral video/image recordings into a "
                        "BEP047 BIDS dataset; media metadata via ffprobe."
                    ),
                }
            ],
            "ReferencesAndLinks": [
                "https://github.com/bids-standard/bids-specification/pull/2231",
            ],
        }
        write_json(self.bids_dir / "dataset_description.json", desc, self.dry_run)

        readme = (
            f"# {self.dataset_name}\n\n"
            "Behavioral video and image recordings organized under the BIDS "
            "`beh` datatype following BEP047 (audio/video/image recordings).\n\n"
            "Generated from `sourcedata/raw` by `code/convert_raw_to_bids.py`.\n\n"
            "- `_video` / `_audiovideo`: overhead behavioral recordings (MP4).\n"
            "- `_image`: still frames / average frames (PNG).\n"
            "- The `recording-<camera>` entity identifies the camera view.\n"
            "- Lab tracking / conversion parameters from the source `*.settings` "
            "files are preserved in each media sidecar under `TrackingSettings`.\n\n"
            "Media metadata was extracted with FFmpeg's `ffprobe`.\n"
        )
        write_text(self.bids_dir / "README", readme, self.dry_run)

        participants_tsv = (
            "participant_id\tspecies\n"
            f"sub-{self.subject}\t{self.species}\n"
        )
        write_text(self.bids_dir / "participants.tsv", participants_tsv, self.dry_run)
        participants_json = {
            "participant_id": {"Description": "Unique participant identifier."},
            "species": {
                "Description": (
                    "Binomial species name. `sub-multi` aggregates the multiple "
                    "individuals tracked within each recording."
                )
            },
        }
        write_json(self.bids_dir / "participants.json", participants_json, self.dry_run)

    def write_scans(self) -> None:
        scans_json = {
            "filename": {
                "Description": "Path to the media file, relative to the subject directory."
            },
            "acq_time": {
                "Description": (
                    "Acquisition time (ISO 8601). Taken from the media file's "
                    "embedded creation time when available, otherwise derived "
                    "from the session date at 00:00:00."
                )
            },
        }
        for ses_label, rows in self.scans.items():
            if not rows:
                continue
            sub_ses = f"sub-{self.subject}_ses-{ses_label}"
            ses_dir = self.bids_dir / f"sub-{self.subject}" / f"ses-{ses_label}"
            lines = ["filename\tacq_time"]
            lines += [f"{name}\t{when}" for name, when in sorted(rows)]
            write_text(ses_dir / f"{sub_ses}_scans.tsv", "\n".join(lines) + "\n", self.dry_run)
            write_json(ses_dir / f"{sub_ses}_scans.json", scans_json, self.dry_run)

    # -- top-level entry point -------------------------------------------- #
    def run(self) -> int:
        if not self.raw_dir.is_dir():
            self.log(f"ERROR: raw directory not found: {self.raw_dir}")
            return 2
        sessions = self.session_dirs()
        if not sessions:
            self.log(f"ERROR: no session directories under {self.raw_dir}")
            return 2

        for session_dir in sessions:
            self.convert_session(session_dir)

        self.write_dataset_files()
        self.write_scans()

        self.log("")
        self.log(f"Converted {self.converted} media file(s) into {self.bids_dir}")
        if self.skipped_files:
            self.log(f"Ignored {len(self.skipped_files)} non-media file(s) "
                     f"(e.g. notes.txt, *.srt, *.pv, *.results).")
            for path in self.skipped_files:
                self.vlog(f"  ignored: {path.relative_to(self.raw_dir)}")
        if self.warnings:
            self.log(f"{len(self.warnings)} warning(s):")
            for warning in self.warnings:
                self.log(f"  - {warning}")
        if self.dry_run:
            self.log("(dry run: no files were written)")
        return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a sourcedata/raw behavioral-recording tree into a "
                    "BEP047 BIDS dataset (sourcedata/rawbids).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("sourcedata/raw"),
                        help="Input raw directory (one session per sub-directory).")
    parser.add_argument("--bids-dir", type=Path, default=Path("sourcedata/rawbids"),
                        help="Output BIDS dataset directory.")
    parser.add_argument("--subject", default="multi",
                        help="BIDS subject label (without the sub- prefix).")
    parser.add_argument("--link", dest="link_mode", default="copy",
                        choices=["copy", "symlink", "hardlink", "move"],
                        help="How to place media files into the BIDS tree.")
    parser.add_argument("--ffprobe", dest="ffprobe_bin", default="ffprobe",
                        help="Path to the ffprobe executable.")
    parser.add_argument("--count-frames", action="store_true",
                        help="Ask ffprobe to count frames exactly (slower, accurate).")
    parser.add_argument("--skip-metadata", action="store_true",
                        help="Do not run ffprobe; write sidecars from *.settings only.")
    parser.add_argument("--device", default=None,
                        help="Override the Device sidecar field for all media.")
    parser.add_argument("--species", default="n/a",
                        help="Value for the participants.tsv species column "
                             "(e.g. 'Ovis aries').")
    parser.add_argument("--dataset-name", default="Kemere lab behavioral recordings",
                        help="dataset_description.json Name.")
    parser.add_argument("--author", dest="authors", action="append", default=None,
                        help="Author for dataset_description.json (repeatable).")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing output files.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report actions without writing anything.")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print per-file mapping details.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    converter = Converter(
        raw_dir=args.raw_dir,
        bids_dir=args.bids_dir,
        subject=sanitize_label(args.subject) or "multi",
        link_mode=args.link_mode,
        ffprobe_bin=args.ffprobe_bin,
        count_frames=args.count_frames,
        skip_metadata=args.skip_metadata,
        device=args.device,
        species=args.species,
        dataset_name=args.dataset_name,
        authors=args.authors or ["Kemere Lab"],
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    try:
        return converter.run()
    except FFprobeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Hint: install FFmpeg (which provides ffprobe), or re-run with "
              "--skip-metadata to write sidecars without media properties.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
