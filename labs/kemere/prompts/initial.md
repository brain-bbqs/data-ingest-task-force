# Session: BEP047 raw-to-BIDS conversion for the Kemere lab

A working log of building a conversion pipeline that turns a `sourcedata/raw`
tree of behavioral drone/overhead recordings into a standardized BIDS dataset
(following [BEP047](https://github.com/bids-standard/bids-specification/pull/2231))
under `sourcedata/rawbids`, then containerizing it and adding a golden-file
integration test.

- **Repo:** `brain-bbqs/kemere-R34DA059514-ingest`
- **Branch:** `claude/bids-video-conversion-script-6e8r33`
- **PR:** [#1](https://github.com/brain-bbqs/kemere-R34DA059514-ingest/pull/1)

---

## Request 1 — Build the conversion script

> Hi can you make a conversion script for the following `sourcedata/raw` filetree of dandiset `000477`:
>
> ```
> 000477
> ├── dandiset.yaml
> └── sourcedata
>     └── raw
>         └── 07102026-Session1
>             └── overhead
>                 └── beh
>                     ├── average_overhead_video.png
>                     ├── notes.txt
>                     ├── overhead_dji_metadata.srt
>                     ├── overhead_video.mp4
>                     ├── overhead_video.pv
>                     ├── overhead_video.results
>                     ├── overhead_video.settings
>                     └── single_frame.png
> ```
>
> Into a standardized BIDS structure `sourcedata/rawbids/sub-multi/ses-<id>`
> following BEP047 (use `ffmpeg` to get metadata for JSON).
>
> Focus right now only on the `.mp4` files; the `.settings` files are raw text with rough structure like
>
> ```
> calculate_posture = false
> cm_per_pixel = 3.687
> detect_size_filter = [[10,100000]]
> detect_threshold = 15
> detect_type = background_subtraction
> meta_encoding = rgb8
> meta_real_width = 3840
> meta_source_path = "/Users/ckemere/Data/Sheep/Michigan-July-2026/07102026-Session1/overhead/beh/overhead_video.mp4"
> track_background_subtraction = true
> track_max_individuals = 25
> track_max_speed = 960
> video_conversion_range = [0,99613]
> ```
>
> which can be added as extra metadata to the sidecar JSON. Also include the `.png` files as `_image` type.
>
> Refs: [Example dataset](https://github.com/bids-standard/bids-examples/tree/da6cf131e2e40ce731f8e74a818ad3e7e28ebb2a/beh_audio_video_recordings)
> and [specification](https://github.com/bids-standard/bids-specification/pull/2231)

### What I did

1. **Researched the BEP047 schema** directly from PR #2231 (commit `07ca171`) — the
   `beh` file-naming rules, the media/beh sidecar rules, the suffix/entity objects,
   and the metadata field definitions — plus the reference example dataset's file
   names and JSON sidecars.
2. Confirmed the load-bearing details:
   - Suffixes/extensions: `video`=`.mp4/.mkv/.avi`, `audiovideo`=same, `image`=`.jpg/.png`.
   - Entities (subject required, rest optional): `sub, ses, task, acq, run, recording, split` (canonical order).
   - Sidecar fields per suffix, with types (e.g. `VideoFrameCount` integer≥1, `RecordingDuration` number>0).
   - `scans.tsv` `filename` is `participant_relative` → includes the `ses-<label>/` prefix.
3. Established the mapping:

   | Source | BIDS output |
   |---|---|
   | `07102026-Session1/` | `ses-20260710` (ISO date; `sNN` for 2nd+ session/day) |
   | `overhead/` (camera) | `recording-overhead` entity |
   | `overhead_video.mp4` | `sub-multi_ses-20260710_recording-overhead_video.mp4` (`audiovideo` if audio detected) |
   | `overhead_video.settings` | merged into the video JSON under `TrackingSettings` |
   | `average_overhead_video.png` | `sub-multi_ses-20260710_acq-average_recording-overhead_image.png` |
   | `single_frame.png` | `sub-multi_ses-20260710_acq-singleframe_recording-overhead_image.png` |

4. Wrote **`code/convert_raw_to_bids.py`** (standard-library only; shells out to
   `ffprobe`). It extracts media metadata, coerces `.settings` values to native
   types (bools, floats, nested lists like `[[10,100000]]`), builds BIDS filenames
   and sidecars, auto-selects `video` vs `audiovideo` from the presence of an audio
   stream, and generates `dataset_description.json`, `README`, `participants.tsv/json`,
   and per-session `scans.tsv/json`.
5. **Tested it** — `ffprobe` wasn't installed in the sandbox, so I used
   `imageio-ffmpeg` (bundled `ffmpeg` binary) to generate real fixtures and a
   PyAV-backed `ffprobe` shim to exercise the real parsing path. Ran the converter
   against a faithful reconstruction of the exact filetree.

Example generated video sidecar:

```json
{
  "RecordingDuration": 2.0,
  "VideoCodec": "h264",
  "VideoFrameRate": 30.0,
  "VideoFrameCount": 60,
  "ImageWidth": 640,
  "ImageHeight": 360,
  "ImagePixelFormat": "yuv420p",
  "ImageBitDepth": 8,
  "DevicePosition": "overhead",
  "TrackingSettings": {
    "Description": "Raw parameters from the Kemere-lab tracking / video-conversion pipeline, preserved verbatim from the source `*.settings` file for provenance. Not part of the BIDS specification.",
    "SourceFile": "overhead_video.settings",
    "Parameters": {
      "cm_per_pixel": 3.687,
      "track_max_individuals": 25,
      "video_conversion_range": [0, 99613]
    }
  }
}
```

6. Did a focused inline review, which caught two real issues (both fixed + tested):
   - RFC 6381 codec strings must use **lowercase** hex (`avc1.4d001f`, not `4D001F`).
   - The per-session filename-uniqueness set was recreated per source folder, so two
     folders mapping to the same session label could clobber each other → made the
     set per-label.

### Naming decisions (documented, easy to change)

- **Session id:** ISO date from the folder (`ses-20260710`); `sNN` suffix for a 2nd+
  session the same day. One function, `derive_session_label`.
- **`recording-overhead`:** the `recording` entity for the camera view (per the spec's
  "simultaneous recordings from different angles"), plus `DevicePosition: "overhead"`.
- **Image `acq` labels:** derived from filenames (`average`, `singleframe`) since `desc`
  isn't allowed for `image` in the schema.

Out of scope per the request: the DJI `.srt` GPS track and `notes.txt` are reported and
ignored, not converted.

---

## Request 2 — Environment + containerization

> Can you also specify a basic python environment that could run all this? And
> containerize it? Much like as seen on
> [dandi-cache/content-id-to-dandiset-paths](https://github.com/dandi-cache/content-id-to-dandiset-paths).

I mirrored that repo's layout and philosophy:

```
envs/pyproject.toml     loose, unpinned env declaration + [test] / [dev] extras
envs/.python-version    3.13
containers/Dockerfile   neurodebian:trixie base + FFmpeg, PEP-668 venv
.github/workflows/      build_and_upload_docker_image.yml (→ GHCR) + test.yml
pyproject.toml          ruff config
```

Same principle: the environment is **not pinned** — the Dockerfile resolves it fresh
and the image digest is the reproducibility lock (no lockfile). The image holds only
the environment; code and data are mounted at run time:

```bash
docker run --rm -v "$PWD":/work -w /work \
  ghcr.io/brain-bbqs/kemere-r34da059514-ingest:latest \
  python code/convert_raw_to_bids.py \
    --raw-dir 000477/sourcedata/raw --bids-dir 000477/sourcedata/rawbids --species "Ovis aries"
```

The one adaptation: the converter is standard-library only, so its real dependency is
the *system* FFmpeg package (the analogue of their `git-annex`), and `dependencies` in
`envs/pyproject.toml` is empty — the only Python packages are the test-only extras.

---

## Request 3 — Golden-file testing

> For the testing, focus much less on little unit tests and instead use an explicit
> mock example rather like that seen on
> [dandi/s3-log-extraction](https://github.com/dandi/s3-log-extraction/tree/main/tests/example_logs)
> → [expected_output](https://github.com/dandi/s3-log-extraction/tree/main/tests/expected_output).
> Then only one integration test of the actual running of the conversion script on the
> mocked example inputs to ensure they match outputs.

Replaced the unit-test collection with that fixture pattern:

- `tests/example_raw/` — committed mock of the exact filetree (7 KB mp4, two 1 KB pngs,
  the `.settings`, plus `notes.txt`/`.srt`/`.pv`/`.results`).
- `tests/expected_output/` — the golden BIDS tree.
- `tests/test_conversion.py` — **one** integration test: runs the converter and asserts
  the produced dataset matches the golden tree (JSON compared semantically, text/media
  byte-exact).
- `tests/generate_fixtures.py` — regenerates both fixtures on intentional changes.

`ffprobe` is backed by the committed PyAV shim so the test is deterministic and needs no
system FFmpeg; the golden values come out clean (`RecordingDuration: 1.0`,
`VideoFrameCount: 30`).

---

## Deliberate calls worth flagging

- **ruff only** (skipped black, which would explode the hand-tuned codec/pix_fmt lookup tables).
- The image installs the `[test]` extra so it can self-validate.
- Couldn't build the image in-sandbox (docker CLI present, no daemon) — the CI workflow
  builds it on push. Everything else (integration test, ruff, the `pip install ./envs[test]`
  CI mechanic) was verified green.

---

## Final layout

```
.github/workflows/
  build_and_upload_docker_image.yml
  test.yml
code/
  convert_raw_to_bids.py
  README.md
containers/
  Dockerfile
envs/
  pyproject.toml
  .python-version
tests/
  example_raw/…                (mock input tree)
  expected_output/…            (golden BIDS output)
  test_conversion.py           (the one integration test)
  generate_fixtures.py
  ffprobe_shim.py
pyproject.toml                 (ruff)
README.md
.gitignore
```

## Commits

- `Add BEP047 BIDS conversion script for raw behavioral recordings`
- `Add containerized environment and golden-file integration test`
