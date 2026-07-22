#!/usr/bin/env python3
"""A minimal ``ffprobe``-compatible shim backed by PyAV.

This exists purely for testing ``convert_raw_to_bids.py`` in environments where
the real ``ffprobe`` binary is unavailable. It emulates just enough of

    ffprobe -v error -print_format json -show_format -show_streams [-count_frames] FILE

to exercise the converter's metadata-parsing paths against real media files.
It is NOT a drop-in replacement for ffprobe in production.
"""

from __future__ import annotations

import json
import sys
from fractions import Fraction

import av


def _rate_str(rate) -> str:
    if not rate:
        return "0/0"
    fr = Fraction(rate)
    return f"{fr.numerator}/{fr.denominator}"


def probe(path: str, count_frames: bool) -> dict:
    container = av.open(path)
    streams_out = []
    for index, stream in enumerate(container.streams):
        cc = stream.codec_context
        entry: dict = {
            "index": index,
            "codec_type": stream.type,
            "codec_name": getattr(cc, "name", None),
        }
        try:
            tag = stream.codec_tag
            if tag:
                entry["codec_tag_string"] = tag
        except Exception:
            pass

        if stream.type == "video":
            width = getattr(cc, "width", None) or getattr(stream, "width", None)
            height = getattr(cc, "height", None) or getattr(stream, "height", None)
            pix_fmt = None
            fmt = getattr(cc, "format", None) or getattr(stream, "format", None)
            if fmt is not None:
                pix_fmt = fmt.name
            if width is None or height is None or pix_fmt is None:
                try:
                    frame = next(container.decode(video=0))
                    width = width or frame.width
                    height = height or frame.height
                    pix_fmt = pix_fmt or frame.format.name
                    container.seek(0)
                except Exception:
                    pass
            if width:
                entry["width"] = int(width)
            if height:
                entry["height"] = int(height)
            if pix_fmt:
                entry["pix_fmt"] = pix_fmt
            avg = getattr(stream, "average_rate", None)
            entry["avg_frame_rate"] = _rate_str(avg)
            entry["r_frame_rate"] = _rate_str(getattr(stream, "base_rate", None) or avg)
            frames = getattr(stream, "frames", 0) or 0
            if count_frames:
                frames = sum(1 for _ in container.decode(video=0))
                container.seek(0)
            if frames:
                entry["nb_frames"] = str(frames)
            profile = getattr(cc, "profile", None)
            if profile:
                entry["profile"] = profile
            level = getattr(cc, "level", None)
            if isinstance(level, int) and level > 0:
                entry["level"] = level

        elif stream.type == "audio":
            sample_rate = getattr(cc, "sample_rate", None)
            if sample_rate:
                entry["sample_rate"] = str(sample_rate)
            channels = getattr(cc, "channels", None)
            if channels is None:
                layout = getattr(cc, "layout", None)
                channels = getattr(layout, "nb_channels", None) if layout else None
            if channels:
                entry["channels"] = int(channels)
            profile = getattr(cc, "profile", None)
            if profile:
                entry["profile"] = profile

        metadata = dict(stream.metadata or {})
        if metadata:
            entry["tags"] = metadata
        streams_out.append(entry)

    fmt: dict = {"filename": path, "nb_streams": len(container.streams)}
    if container.duration is not None:
        fmt["duration"] = f"{container.duration / av.time_base:.6f}"
    fmt_meta = dict(container.metadata or {})
    if fmt_meta:
        fmt["tags"] = fmt_meta
    container.close()
    return {"streams": streams_out, "format": fmt}


def main(argv: list[str]) -> int:
    count_frames = "-count_frames" in argv
    # The file path is the final non-flag argument.
    path = None
    skip_next = False
    flag_takes_value = {"-v", "-print_format", "-show_entries", "-select_streams"}
    for i, token in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if token in flag_takes_value:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        path = token
    if not path:
        print("ffprobe_shim: no input file", file=sys.stderr)
        return 1
    json.dump(probe(path, count_frames), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
