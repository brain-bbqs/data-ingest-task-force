# `convert_raw_to_bids.py`

Convert a `sourcedata/raw` tree of Kemere-lab behavioral recordings into a
standardized BIDS dataset under `sourcedata/rawbids`, following
[BEP047](https://github.com/bids-standard/bids-specification/pull/2231)
(audio / video / image recordings in the `beh` datatype).

## What it does

For each session directory it discovers media files and reorganizes them into
BIDS, generating a JSON sidecar for every file:

| Source | BIDS output (suffix) |
| --- | --- |
| `*.mp4` (no audio stream) | `_video` |
| `*.mp4` (with audio stream) | `_audiovideo` |
| `*.png`, `*.jpg` | `_image` |
| `*.wav`, `*.flac`, `*.mp3`, `*.ogg` | `_audio` |
| `*.settings` | merged into the matching media sidecar under `TrackingSettings` |
| `notes.txt`, `*.srt`, `*.pv`, `*.results`, … | ignored (reported in the summary) |

Media metadata (`VideoCodec`, `VideoFrameRate`, `VideoFrameCount`,
`RecordingDuration`, `ImageWidth`, `ImageHeight`, `ImagePixelFormat`,
`ImageBitDepth`, audio properties, and a best-effort `VideoCodecRFC6381`) is
extracted with FFmpeg's `ffprobe`.

### Naming

The raw layout `<MMDDYYYY>-Session<N>/<camera>/beh/<file>` maps to:

```
sub-multi/
  ses-<YYYYMMDD>/
    sub-multi_ses-<YYYYMMDD>_scans.tsv
    beh/
      sub-multi_ses-<YYYYMMDD>_recording-<camera>_video.mp4        (+ .json)
      sub-multi_ses-<YYYYMMDD>_acq-<label>_recording-<camera>_image.png (+ .json)
```

- **Session label** — ISO date from the folder name (`07102026-Session1` →
  `ses-20260710`). A 2nd+ session on the same day gets an `sNN` suffix
  (`ses-20260710s02`). Override per run with `--subject`/edit `derive_session_label`.
- **`recording-<camera>`** — the camera sub-directory (e.g. `overhead`),
  which distinguishes simultaneous views per BEP047.
- **`acq-<label>`** for images — derived from the file name so multiple stills
  under one camera stay distinct (`average_overhead_video.png` → `acq-average`,
  `single_frame.png` → `acq-singleframe`).

## Requirements

- Python 3.9+ (standard library only).
- [FFmpeg](https://ffmpeg.org/) on `PATH` (provides `ffprobe`).
  - macOS: `brew install ffmpeg`
  - Debian/Ubuntu: `sudo apt install ffmpeg`

## Usage

```bash
# From the dandiset root (the directory containing sourcedata/):
python3 code/convert_raw_to_bids.py \
    --raw-dir  sourcedata/raw \
    --bids-dir sourcedata/rawbids \
    --species  "Ovis aries"

# Preview without writing anything:
python3 code/convert_raw_to_bids.py --dry-run --verbose

# Place large videos without copying:
python3 code/convert_raw_to_bids.py --link symlink   # or hardlink / move
```

Useful options: `--ffprobe /path/to/ffprobe`, `--count-frames` (exact frame
count, slower), `--skip-metadata` (sidecars from `*.settings` only, no ffprobe),
`--device`, `--dataset-name`, `--author`, `--overwrite`. See `--help`.

## Validation

BEP047 is not yet in a released BIDS schema, so validate against the proposal
branch (as the reference example dataset does):

```bash
deno run -A jsr:@bids/validator sourcedata/rawbids \
    --schema https://.../bendichter/bids-specification/audio-video-clean/schema.json
```

## Tests

A single integration test (`tests/test_conversion.py`) runs this script on the
committed mock input tree (`tests/example_raw/`) and asserts the output matches
the committed golden tree (`tests/expected_output/`) — the same
`example_raw` → `expected_output` fixture pattern used in
[`dandi/s3-log-extraction`](https://github.com/dandi/s3-log-extraction/tree/main/tests).

```bash
pip install "../envs[test]"      # pytest + PyAV
python3 -m pytest ../tests/ -q   # (or run `pytest tests/ -q` from the repo root)
```

`ffprobe` is provided by `tests/ffprobe_shim.py` (a small PyAV-backed stand-in
used only for testing), so the run is deterministic and needs no system
`ffprobe`. To regenerate the fixtures after an intentional change, install the
`dev` extra and run `python3 tests/generate_fixtures.py`.
