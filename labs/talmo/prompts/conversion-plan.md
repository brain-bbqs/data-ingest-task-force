# Talmo lab conversion plan (MouseDyad-10M and SLAP-2M)

Status: approved by the requester on 2026-11-25, with the decisions quoted in Requests 2 and 4 of [the request record](initial.md). Questions still open are tracked in [`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md).

The request record is [`initial.md`](initial.md).

## Amendments after approval

The requester's decisions in Requests 2 and 4 changed the draft below. Where the two differ, this list wins. The mapping tables as built are in [`../code/README.md`](../code/README.md).

- The raw BIDS dataset sits in a top-level `rawbids/`, the BIDS 1.11.2 study convention. The lab's own documents go to the study's `sourcedata/`, not `derivatives/pose/docs/`.
- MouseDyad-10M has one subject per unique pair of animals, labeled by the two sorted animal IDs (`sub-181313x181321`). SLAP-2M has no animal IDs and keeps `sub-multi`.
- All derivatives sit in one dataset, `derivatives/pipeline-luc3d/`, with the models in its `models/` folder (Request 4). An interim build split them into `derivatives/sleap/` and `derivatives/triangulation/`.
- The lab's dataset cards, found after the draft, correct two intake facts. A track name is `<animal ID>_<number of tail marks>`, so MouseDyad-10M has 9 mice in 18 pairings, not 15 and 24. Track 0 is the male and track 1 the female.
- The cards also supply strains, the MIT license and "hardware-synchronized" for MouseDyad-10M. These fill parts of questions 6 and 9.
- The SLAP-2M side-camera predictions are named `desc-predictions`, not `desc-sidemodel`, matching MouseDyad-10M.
- Not built from the draft: the check of every source file against `manifest.csv`. Files no rule covers are reported by walking each session folder instead.
- New questions Q11 (triangulation tool), Q12 (validation), Q13 (derivative names, since resolved) and Q14 (per-animal metadata) were added.

## Questions for review

These are the questions as put to the requester with the draft. Their answers are in Request 2.

1. **Where the raw BIDS dataset sits in the study.** You asked for "the sourcedata being the BEP047 valid behavioral videos", and Kemere uses `sourcedata/rawbids/`. The current BIDS spec text for study datasets (master, `1.11.3-dev`, after [bids-specification#2191](https://github.com/bids-standard/bids-specification/pull/2191)) instead reserves a top-level `rawbids/` for the raw BIDS dataset and keeps `sourcedata/` for non-BIDS source. Default: `sourcedata/rawbids/`, matching your wording and Kemere. Say so if you want top-level `rawbids/`.
2. **Subject model.** Every video shows 1 to 4 mice, so no file belongs to one animal. Default: one `sub-multi` (Kemere precedent), with the per-session roster in `sub-multi_sessions.tsv`. MouseDyad-10M has real mouse ids (15 mice, from the 3D files). SLAP-2M has only counts per coat color. The alternative for MouseDyad-10M is one subject per pair (24 pairings), which gives 24 subject folders and still no per-animal files.
3. **Pose files keep their native formats.** BIDS has no pose standard I could verify (the BEP index host was unreachable from here). Default: SLEAP `.slp`, analysis `.h5`, 3D `.h5` and anipose `.toml` files are copied byte-for-byte under BIDS-style names with a `_pose` or `_calibration` suffix, each with a JSON sidecar describing shape, axes, units, nodes and provenance. No conversion to another container. These suffixes are not in the BIDS schema, so the derivative dataset is "BIDS to the extent possible".
4. **One derivative dataset or several.** Default: one `derivatives/pose/` holding 2D pose, 3D pose and calibration, plus `derivatives/models/` holding the SLEAP models verbatim as a non-BIDS derivative. The alternative splits by pipeline (`sleap/`, `sleap-anipose/`).
5. **Models and training labels (5.3 GB in total).** Default: included verbatim under `derivatives/models/`. Say so if they should stay out of the standardized dandisets.
6. **Camera timing.** BEP047 now requires `StartTime` on every file with a `recording` entity. Default: `StartTime: 0` for every camera, on the README's statement that cameras are synchronized and the 3D is aligned by frame index. In SLAP-2M the per-camera filename timestamps differ by 6 to 18 s within a session while frame counts are identical, so I read them as file-creation times, not start offsets. In MouseDyad-10M cameras differ by 0 to 11 frames. The value is `PROVISIONAL` until the lab confirms hardware triggering.
7. **Lab key.** Default `talmo`, as you and the dandiset name ("Incoming: Talmo U01DA063581") call it. The house rule is the PI surname, which would be `pereira`.
8. **Three stray files** in SLAP-2M end in `.proofread.slpanalysis.h5` (sessions `10212022175626` top and topL, `10212022181154` back), beside the regular `.proofread.slp.analysis.h5`. Default: reported and not converted.
9. **Metadata nobody supplied.** Sex, age or date of birth, strain and genotype of the mice. Institution per collection (file paths inside MouseDyad-10M point at a Princeton Falkner-lab server, SLAP-2M at a Talmo-lab share). Experimenters, associated papers, license, camera make and model, timezone of the timestamps, and the meaning of `experimental_code` (`ACL2MSFSd/e/m/p`). All are carried as `PROVISIONAL` or `n/a`, never invented.
10. **Which 2D track is which mouse** in MouseDyad-10M. The 3D files name tracks by mouse id. The 2D files say `track_0` and `track_1`. The sidecars will state that the mapping is unconfirmed.

## Completed intake

| Field | Recorded value and source |
| --- | --- |
| Lab key | `talmo` (see question 7) |
| Layout | Flat `labs/talmo/`, one converter, two datasets (`mouse-dyad-10m`, `slap-2m`). The two source layouts differ, but the output conventions are identical, so they share a codebase (Sanes precedent). |
| PI, institution, contact | Talmo Pereira lab. Institution and contact not supplied, `PROVISIONAL`. |
| Award | `U01DA063581`, from the `000641` dandiset metadata |
| Incoming | `000641` "Incoming: Talmo U01DA063581", 4,402 assets, 408 GB, embargoed |
| Standardized | `sourcedata/raw/luc3d/MouseDyad-10M` → `000643` ("Standardized: mouse-dyad-10M"). `sourcedata/raw/luc3d/SLAP-2M` → `000642` ("Standardized: slap-2m"). Both exist and are empty. |
| Archive | `ember-dandi` |
| Species | `Mus musculus`. The lab READMEs say mice. |
| Behavior | MouseDyad-10M is freely interacting mouse pairs. SLAP-2M is 1 to 4 mice in an arena with obstacles, difficulty 0 to 7. |
| Modalities | Multi-camera grayscale video, 2D pose (SLEAP), 3D pose (triangulated), camera calibration, trained pose models. No audio, no neural data. |
| Acquisition | MouseDyad-10M has 5 cameras named by serial number, 1280×1024, about 150.1 fps. SLAP-2M has 8 named cameras, 1280×1024, 30 fps (60 fps for the 13 sessions of 2022-10-19). Camera hardware not supplied. |
| Papers | None supplied |
| Target | BIDS study dataset. Raw part is BEP047 video with rich sidecars. Pose and the rest under `derivatives/`. Named by the requester. |
| Expected-output example | None supplied beyond "similar to Kemere lab" |
| Prior conversion work | None. The Kemere converter is the in-repo model. |
| Volume | MouseDyad-10M is 56 sessions, 280 videos (105.5 GB), 72.0 GB of pose and calibration, 4.2 GB of models. SLAP-2M is 74 sessions, 592 videos (188.9 GB), 36.4 GB of pose and calibration, 1.1 GB of models. |
| Operational | `ffprobe` per video (container metadata only, no decode). `h5py` to read shapes and provenance from `.h5` and `.slp`. Videos are placed by copy or link, never re-encoded. |

### Evidence actually inspected

- The full asset listing of `000641` from the archive API (paths and sizes of all 4,402 assets), checked against both lab `manifest.csv` files. Sizes agree for every file.
- Read in full: both lab `README.md` files, both `manifest.csv`, `master_sheet.tsv`, `master_sheet_side_model.tsv`, both `qc_sessions.csv` and `qc_views.csv`, `mouse_skeleton.toml` (identical in both), the upload tool's `.transfer/*.json` log.
- Downloaded and opened one representative of each remaining kind. For MouseDyad-10M session `20250827_141755`: the 3D `.h5`, one camera `.mp4` (ffprobe) and its `.analysis.h5`, `calibration.toml`, `cboard.toml`, `calibration.metadata.h5`. For SLAP-2M session `10072022120554`: `points3d.h5`, `aligned_points3d.h5`, `aligned_cage_points3d.h5`, `reprojections.h5`, `calibration.toml`, `alignment.toml`, one `.mp4` (ffprobe), and one each of `.predictions.proofread.slp`, its `.analysis.h5`, `.reprojections.slp`, its `.h5`, and the side-model `.predictions.slp`.
- Not opened: every other session's binaries, the MouseDyad-10M per-camera `.slp` files (168 MB each), and anything under `models/`.
- BEP047 was read from the schema files of [bids-specification#2231](https://github.com/bids-standard/bids-specification/pull/2231) at head `61fdc19`. The study layout was read from `src/common-principles.md` on bids-specification master.

### Things the tree showed that the READMEs do not say

- The upload renamed the model folders. `=` became `_` (`…centroid_N=39644` is `…centroid_N_39644` in the archive), so those 78 manifest paths do not match the archive literally.
- The 17 SLAP-2M sessions of 2022-10-30 name their pose files `…_h265_10bit_CRF30_…`, not `…_h265_CRF30_…`.
- The upload log lists 8 errored transfers. All 8 files are present in the archive at the manifest size, so they were retried successfully.
- The MouseDyad-10M session folder time and its file timestamp differ by about 9 s (`20250827_141755` holds `…-20250827141804.*`).
- `master_sheet.tsv` and `master_sheet_side_model.tsv` have the same columns. They differ in which file the `side` and `sideL` columns point at.

## Standard and granularity

BIDS, as named in the request. Each standardized dandiset is one BIDS study dataset:

```
<standardized>/                      DatasetType "study"
  dataset_description.json
  README
  sourcedata/rawbids/                DatasetType "raw", BEP047 videos
  derivatives/pose/                  DatasetType "derivative"
  derivatives/models/                verbatim, non-BIDS
```

One BIDS session per source session. Videos and pose files are never re-encoded or rewritten. A session converts independently of the others, so sessions run in parallel as in Kemere.

## Identity rules

Each rule lives in one function, so it is easy to change.

| Rule | MouseDyad-10M | SLAP-2M |
| --- | --- | --- |
| Session directory | `sessions/<YYYYMMDD_HHMMSS>/` | `sessions/<YYYY-MM-DD>/<MMDDYYYYHHMMSS>/` |
| Dispatch include glob | `sourcedata/raw/luc3d/MouseDyad-10M/sessions/*` | `sourcedata/raw/luc3d/SLAP-2M/sessions/*/*` |
| Session label | Folder name without the underscore. `20250827_141755` → `ses-20250827141755` | Folder name reordered to ISO. `10072022120554` → `ses-20221007120554` |
| Subject label | `sub-multi` | `sub-multi` |
| `recording` label | Camera serial folder. `21241563` → `recording-21241563` | Camera folder. `backL` → `recording-backL` |
| `acq_time` in `scans.tsv` | File timestamp, `2025-08-27T14:18:04`, same for all cameras | Session folder timestamp, `2022-10-07T12:05:54`, same for all cameras |

Session basenames are unique across each collection, as dispatch requires (56 and 74 distinct names).

## Mapping, MouseDyad-10M → 000643

`<ses>` stands for `sub-multi_ses-20250827141755`. Raw paths are under `sourcedata/rawbids/sub-multi/ses-…/beh/`. Derivative paths are under `derivatives/pose/sub-multi/ses-…/beh/`.

| Source | Output |
| --- | --- |
| `sessions/<s>/<serial>/<serial>-<ts>.mp4` | raw `<ses>_recording-<serial>_video.mp4` plus `.json` sidecar |
| `sessions/<s>/calibration/<cts>_calibration.toml` | derivative `<ses>_calibration.toml`. Each camera's block is also merged into that camera's video sidecar under `CameraCalibration`. |
| `sessions/<s>/calibration/<cts>_cboard.toml` | derivative `<ses>_desc-board_calibration.toml`. Absent for the 6 sessions of `20250908_*`, which is reported. |
| `sessions/<s>/calibration/<cts>_calibration.metadata.h5` | derivative `<ses>_desc-detections_calibration.h5` plus `.json`. Absent for the same 6 sessions. |
| `sessions/<s>/<serial>/<serial>-<ts>.slp` | derivative `<ses>_recording-<serial>_desc-predictions_pose.slp` plus `.json` |
| `sessions/<s>/<serial>/<serial>-<ts>.analysis.h5` | derivative `<ses>_recording-<serial>_desc-predictions_pose.h5` plus `.json` |
| `sessions/<s>/<ts>_points3d_translated_rotated_metric.h5` | derivative `<ses>_desc-arena_pose.h5` plus `.json` (3D, meters, arena frame). Its `track_names`, `experimental_code` and `recording_frame_rate` also feed `sessions.tsv`. |
| `qc_sessions.csv` | per-session columns merged into `sub-multi_sessions.tsv`. Verbatim copy in `derivatives/pose/docs/`. |
| `qc_views.csv` | verbatim copy in `derivatives/pose/docs/`. Video properties are measured fresh with `ffprobe` and compared against it. A mismatch is reported. |
| `mouse_skeleton.toml` | nodes and edges merged into every pose sidecar. Verbatim copy in `derivatives/pose/docs/`. |
| `README.md` | verbatim copy in `derivatives/pose/docs/`. Its facts and known issues are folded into the generated `README` files. |
| `manifest.csv` | verbatim copy in `derivatives/pose/docs/`. Used to check that every source file was seen. |
| `models/**` | `derivatives/models/**`, verbatim, under the archive's sanitized folder names |
| `sourcedata/raw/.transfer/*.json` | out of scope (upload tool log), reported and ignored |
| any file matching no rule above | out of scope, reported by name in the run summary |

## Mapping, SLAP-2M → 000642

`<ses>` stands for `sub-multi_ses-20221007120554`. `<cam>` is one of `back backL mid midL side sideL top topL`. `<enc>` is the historical encoder tag in the name (`h265_CRF30`, `h265_10bit_CRF30`, `h265_CRF12`, `h265_10bit_CRF12`).

| Source | Output |
| --- | --- |
| `<cam>/<cam>-<ts>-0000_h264_CRF20_denoised.mp4` | raw `<ses>_recording-<cam>_video.mp4` plus `.json` sidecar. The per-camera `<ts>` is kept in the sidecar. |
| `calibration.toml` | derivative `<ses>_calibration.toml`. Each camera's block is also merged into that camera's video sidecar under `CameraCalibration`. |
| `alignment.toml` | derivative `<ses>_desc-arena_calibration.toml` plus `.json` (camera-frame to arena-frame transform) |
| `points3d.h5` | derivative `<ses>_desc-camera_pose.h5` plus `.json` (3D, mm, camera frame) |
| `aligned_points3d.h5` | derivative `<ses>_desc-arena_pose.h5` plus `.json` (3D, mm, arena frame) |
| `aligned_cage_points3d.h5` | derivative `<ses>_desc-arenalandmarks_pose.h5` plus `.json` (24 arena landmarks) |
| `reprojections.h5` | derivative `<ses>_desc-reprojections_pose.h5` plus `.json` (all cameras in one file) |
| `<cam>/*_<enc>_denoised.mp4.predictions.proofread.slp` | derivative `<ses>_recording-<cam>_desc-proofread_pose.slp` plus `.json`. Six cameras, not `side` or `sideL`. |
| `<cam>/*.predictions.proofread.slp.analysis.h5` | derivative `<ses>_recording-<cam>_desc-proofread_pose.h5` plus `.json` |
| `<cam>/*.reprojections.slp` | derivative `<ses>_recording-<cam>_desc-reprojections_pose.slp` plus `.json` |
| `<cam>/*.reprojections.slp.h5` | derivative `<ses>_recording-<cam>_desc-reprojections_pose.h5` plus `.json` |
| `side/` and `sideL/` `*.predictions.slp` | derivative `<ses>_recording-<cam>_desc-sidemodel_pose.slp` plus `.json` |
| `<cam>/*.predictions.proofread.slpanalysis.h5` (3 files) | out of scope pending question 8, reported |
| `master_sheet.tsv` | per-session columns merged into `sub-multi_sessions.tsv`. Verbatim copy in `derivatives/pose/docs/`. |
| `master_sheet_side_model.tsv`, `qc_sessions.csv`, `qc_views.csv`, `manifest.csv`, `README.md`, `mouse_skeleton.toml` | same treatment as in MouseDyad-10M |
| `models/**` | `derivatives/models/**`, verbatim |
| any file matching no rule above | out of scope, reported by name in the run summary |

The original file name of every converted file is recorded in its sidecar (`SourceFile`), since the pose file names are the only link back to the lab's sheets.

## Expected output, one MouseDyad-10M session

```
000643/
  dataset_description.json
  README
  sourcedata/
    rawbids/
      dataset_description.json
      README
      participants.tsv
      participants.json
      sub-multi/
        sub-multi_sessions.tsv
        sub-multi_sessions.json
        ses-20250827141755/
          sub-multi_ses-20250827141755_scans.tsv
          sub-multi_ses-20250827141755_scans.json
          beh/
            sub-multi_ses-20250827141755_recording-21241563_video.mp4
            sub-multi_ses-20250827141755_recording-21241563_video.json
            ... (21369048, 21372315, 21372316, 22085397)
  derivatives/
    pose/
      dataset_description.json
      README
      docs/
        README.md  manifest.csv  qc_sessions.csv  qc_views.csv  mouse_skeleton.toml
      sub-multi/
        ses-20250827141755/
          beh/
            sub-multi_ses-20250827141755_calibration.toml
            sub-multi_ses-20250827141755_desc-board_calibration.toml
            sub-multi_ses-20250827141755_desc-detections_calibration.h5
            sub-multi_ses-20250827141755_desc-detections_calibration.json
            sub-multi_ses-20250827141755_desc-arena_pose.h5
            sub-multi_ses-20250827141755_desc-arena_pose.json
            sub-multi_ses-20250827141755_recording-21241563_desc-predictions_pose.slp
            sub-multi_ses-20250827141755_recording-21241563_desc-predictions_pose.h5
            sub-multi_ses-20250827141755_recording-21241563_desc-predictions_pose.json
            ... (four more cameras)
    models/
      sleap-nn/250505_195550.centroid_N_39644/...
      sleap-nn/250505_195550.centered_instance_N_39644/...
      sleap-legacy/...
```

A SLAP-2M session has the same shape with eight cameras and the files of its mapping table.

Example raw video sidecar. Values are the real ones measured from `22085397-20250827141804.mp4` and its `[cam_4]` calibration block.

```json
{
  "RecordingDuration": 1200.494852,
  "StartTime": 0,
  "VideoCodec": "h264",
  "VideoCodecRFC6381": "avc1.640033",
  "VideoFrameRate": 150.1056,
  "VideoFrameCount": 180201,
  "ImageWidth": 1280,
  "ImageHeight": 1024,
  "ImagePixelFormat": "yuv420p",
  "ImageBitDepth": 8,
  "DeviceSerialNumber": "22085397",
  "SourceFile": "sessions/20250827_141755/22085397/22085397-20250827141804.mp4",
  "Synchronization": {
    "Description": "PROVISIONAL. StartTime is 0 on the lab README's statement that the cameras are synchronized. Not part of the BIDS specification.",
    "SourceTimestamp": "20250827141804"
  },
  "CameraCalibration": {
    "Description": "This camera's block of the anipose/sleap-anipose calibration, preserved verbatim. Not part of the BIDS specification.",
    "SourceFile": "sessions/20250827_141755/calibration/20250821100634_calibration.toml",
    "Parameters": {
      "name": "22085397",
      "size": [1280, 1024],
      "matrix": [[1304.9464781478384, 0.0, 639.5], [0.0, 1304.9464781478384, 511.5], [0.0, 0.0, 1.0]],
      "distortions": [-0.1924717848174393, 0.0, 0.0, 0.0, 0.0],
      "rotation": [0.07640046853261817, -0.5083286268360203, -1.504441102216226],
      "translation": [300.03736413759276, -256.54031677882676, 80.70803093280529]
    }
  }
}
```

SLAP-2M video sidecars add `DevicePosition` (the camera name) and a `SourceEncoding` block stating that the file is the lab's x264 CRF 20 re-encode of an HEVC CRF 12 original, per the lab README.

Example derivative sidecar, for `…_desc-arena_pose.json` of the same session:

```json
{
  "Description": "3D pose, translated and rotated into the arena frame.",
  "SourceFile": "sessions/20250827_141755/20250827141804_points3d_translated_rotated_metric.h5",
  "Sources": ["bids:raw:sub-multi/ses-20250827141755/beh/sub-multi_ses-20250827141755_recording-21241563_video.mp4", "..."],
  "Dataset": "tracks",
  "Shape": [180199, 2, 15, 3],
  "Axes": ["frame", "animal", "node", "xyz"],
  "Units": "m",
  "SamplingFrequency": 150.1054,
  "TrackNames": ["181321_0", "181313_3"],
  "NodeNames": ["Nose", "Ear_R", "Ear_L", "TTI", "TailTip", "Head", "Trunk", "Tail_0", "Tail_1", "Tail_2", "Shoulder_left", "Shoulder_right", "Haunch_left", "Haunch_right", "Neck"],
  "Edges": [["TTI", "Head"], ["TTI", "Tail_0"], "..."],
  "ExperimentalCode": "ACL2MSFSd"
}
```

2D pose sidecars carry the same kind of block, plus the provenance stored inside the file (SLEAP or sleap-nn version, model paths, inference timestamps) where it is not empty.

## Metadata plan

| Where | Content |
| --- | --- |
| Study `dataset_description.json` | `Name`, `BIDSVersion`, `DatasetType: "study"`, `Funding: ["NIH U01DA063581"]`. `Authors`, `License` and `ReferencesAndLinks` are `PROVISIONAL` or omitted. |
| Raw `dataset_description.json` | `DatasetType: "raw"`, same funding, `GeneratedBy` naming this converter |
| Derivative `dataset_description.json` | `DatasetType: "derivative"`, `GeneratedBy` listing SLEAP and the triangulation step as the lab README describes them, `SourceDatasets: [{"URL": "../../sourcedata/rawbids/"}]` |
| `participants.tsv` | One row, `sub-multi`, `species` `Mus musculus`. `sex` and `age` are `n/a` (question 9). |
| `sub-multi_sessions.tsv`, MouseDyad-10M | `session_id`, `acq_time`, `source_session`, `animal_count`, `animal_ids` (from the 3D file's `track_names`, for example `181321_0,181313_3`), `experimental_code`, `frame_rate`, `pose3d_frame_count`, `calibration` |
| `sub-multi_sessions.tsv`, SLAP-2M | `session_id`, `acq_time`, `source_session`, `animal_count`, `white_mice`, `agouti_mice`, `black_mice`, `obstacle_rating`, `bedding`, `difficulty`, `frames`, `duration` (as the sheet gives it, blank for six sessions) |
| `scans.tsv` | `filename` (participant-relative), `acq_time` |
| Video sidecars | Everything `ffprobe` reports that BEP047 names, plus `StartTime`, `DeviceSerialNumber` or `DevicePosition`, `SourceFile`, and the namespaced `Synchronization`, `CameraCalibration` and `SourceEncoding` blocks |
| Generated `README` files | The lab README's description and known-issue list, restated, with the verbatim copy under `derivatives/pose/docs/` |

The animal roster comes from the 3D files and the master sheet, not from the 2D tracking files. A MouseDyad-10M session whose 3D file is missing still converts its videos and reports the missing roster.

Timestamps carry no timezone in the source. `acq_time` is written as local time without an offset, which BIDS allows.

## Implementation checks carried into scaffolding

- Validate the raw dataset with the BIDS validator against the BEP047 schema of the reviewed PR head. `StartTime` is required with `recording`, which is newer than the Kemere converter.
- Confirm how the validator treats a `study` dataset and the derivative's non-schema `_pose` and `_calibration` suffixes. Record the outcome. Add a `.bidsignore` only if needed and say so.
- Confirm DANDI upload accepts `sub-multi` BIDS assets for these dandisets as it does for Kemere's.
- Golden test: one mock session per collection under `tests/example_raw/`, built at tiny size, with expected trees under `tests/expected_output/`.
- The converter must fail loudly on a session whose camera set differs from the calibration file's camera list.
