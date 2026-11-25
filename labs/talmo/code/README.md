# `convert_luc3d_to_bids.py`

Converts one Talmo lab LUC3D collection of dandiset `000641` into a BIDS study dataset. The videos become a raw BIDS dataset following [BEP047](https://github.com/bids-standard/bids-specification/pull/2231). The pose products go under `derivatives/` in their native formats.

| Dataset key | Source collection | Standardized dandiset |
| --- | --- | --- |
| `mouse-dyad-10m` | `sourcedata/raw/luc3d/MouseDyad-10M` | `000643` |
| `slap-2m` | `sourcedata/raw/luc3d/SLAP-2M` | `000642` |

Nothing is re-encoded or rewritten. Every video and pose file is copied byte-for-byte under a BIDS name, and a JSON sidecar beside it records what the file holds and where it came from.

## Target structure

```
<standardized>/                          DatasetType "study"
  dataset_description.json
  README
  sourcedata/                            the lab's own documents, verbatim
    README.md  manifest.csv  qc_sessions.csv  qc_views.csv  mouse_skeleton.toml
  rawbids/                               DatasetType "raw"
    dataset_description.json  README  participants.tsv  participants.json
    sub-181313x181321/
      sub-181313x181321_sessions.tsv     (+ .json)
      ses-20250827141755/
        sub-181313x181321_ses-20250827141755_scans.tsv     (+ .json)
        beh/
          sub-181313x181321_ses-20250827141755_recording-21241563_video.mp4   (+ .json)
          ...
  derivatives/
    sleap/                               DatasetType "derivative"
      dataset_description.json  README
      models/                            the SLEAP models, verbatim
      sub-181313x181321/ses-20250827141755/beh/
        ..._recording-21241563_desc-predictions_pose.slp   (+ .h5, one shared .json)
    triangulation/                       DatasetType "derivative"
      dataset_description.json  README
      sub-181313x181321/ses-20250827141755/beh/
        ..._desc-arena_pose.h5                 (+ .json)
        ..._calibration.toml                   (+ .json)
        ..._desc-board_calibration.toml        (+ .json)
        ..._desc-detections_calibration.h5     (+ .json)
```

The study layout follows the BIDS 1.11.2 study convention, with the raw BIDS dataset in a top-level `rawbids/`. `tests/expected_output/` holds a complete small example of both datasets.

## Mapping, MouseDyad-10M

`<ses>` stands for `sub-<pair>_ses-<session>`.

| Source | Output |
| --- | --- |
| `sessions/<s>/<serial>/<serial>-<ts>.mp4` | `rawbids`, `<ses>_recording-<serial>_video.mp4` |
| `sessions/<s>/<serial>/<serial>-<ts>.slp` and `.analysis.h5` | `derivatives/sleap`, `<ses>_recording-<serial>_desc-predictions_pose.slp` and `.h5` |
| `sessions/<s>/<ts>_points3d_translated_rotated_metric.h5` | `derivatives/triangulation`, `<ses>_desc-arena_pose.h5`. Also the source of the animal pair. |
| `sessions/<s>/calibration/*_calibration.toml` | `derivatives/triangulation`, `<ses>_calibration.toml`. Each camera's block is also merged into its video sidecar. |
| `sessions/<s>/calibration/*_cboard.toml` | `derivatives/triangulation`, `<ses>_desc-board_calibration.toml` |
| `sessions/<s>/calibration/*_calibration.metadata.h5` | `derivatives/triangulation`, `<ses>_desc-detections_calibration.h5` |
| `models/**` | `derivatives/sleap/models/**`, verbatim |
| `README.md`, `manifest.csv`, `qc_sessions.csv`, `qc_views.csv`, `mouse_skeleton.toml` | `sourcedata/`, verbatim. The skeleton is also merged into every pose sidecar. |
| anything else | reported in the run summary and not converted |

## Mapping, SLAP-2M

`<ses>` stands for `sub-multi_ses-<session>`. `<cam>` is the camera folder.

| Source | Output |
| --- | --- |
| `<cam>/<cam>-<ts>-0000_h264_CRF20_denoised.mp4` | `rawbids`, `<ses>_recording-<cam>_video.mp4` |
| `<cam>/*.predictions.proofread.slp` and `.slp.analysis.h5` | `derivatives/sleap`, `<ses>_recording-<cam>_desc-proofread_pose.slp` and `.h5` |
| `<cam>/*.mp4.predictions.slp` (side and sideL) | `derivatives/sleap`, `<ses>_recording-<cam>_desc-predictions_pose.slp` |
| `<cam>/*.reprojections.slp` and `.slp.h5` | `derivatives/triangulation`, `<ses>_recording-<cam>_desc-reprojections_pose.slp` and `.h5` |
| `points3d.h5` | `derivatives/triangulation`, `<ses>_desc-camera_pose.h5` |
| `aligned_points3d.h5` | `derivatives/triangulation`, `<ses>_desc-arena_pose.h5` |
| `aligned_cage_points3d.h5` | `derivatives/triangulation`, `<ses>_desc-arenalandmarks_pose.h5` |
| `reprojections.h5` | `derivatives/triangulation`, `<ses>_desc-reprojections_pose.h5` |
| `calibration.toml` | `derivatives/triangulation`, `<ses>_calibration.toml`. Each camera's block is also merged into its video sidecar. |
| `alignment.toml` | `derivatives/triangulation`, `<ses>_desc-arena_calibration.toml` |
| `master_sheet.tsv` | per-session columns of `sub-multi_sessions.tsv`. Verbatim copy in `sourcedata/`. |
| `models/**` and the other documents | as in MouseDyad-10M |
| `<cam>/*.predictions.proofread.slpanalysis.h5` (three stray files) and anything else | reported in the run summary and not converted |

## Naming decisions

Each one lives in a single function of `convert_luc3d_to_bids.py`.

| Decision | Rule | Function |
| --- | --- | --- |
| MouseDyad-10M subject | One subject per unique pair of animals. The two animal IDs, sorted and joined by `x`. `181321` with `181313` is `sub-181313x181321`. | `dyad_subject_label` |
| Animal ID | A track name such as `181321_0` is `<animal ID>_<number of tail marks>`. Only the ID identifies the animal. | `split_track_name` |
| SLAP-2M subject | `sub-multi`. The deposit has animal counts per coat color and no animal IDs. | `SLAP_SUBJECT` |
| MouseDyad-10M session | Folder name without the underscore. `20250827_141755` is `ses-20250827141755`. | `dyad_session_label` |
| SLAP-2M session | Folder name reordered from `MMDDYYYYHHMMSS` to ISO order. `10072022120554` is `ses-20221007120554`. | `slap_session_label` |
| Camera | The camera folder name as the `recording` entity. | `recording_label` |
| `acq_time` | The timestamp in the video names (MouseDyad-10M) or the session folder (SLAP-2M), without a timezone. | `iso_from_label` |

## Sidecars

Video sidecars hold the BEP047 media fields measured with `ffprobe`, `StartTime`, the camera serial number or position, `SourceFile`, and three blocks that are not part of BIDS and say so: `Synchronization`, `CameraCalibration` and (SLAP-2M) `SourceEncoding`.

`StartTime` is 0 for every camera. BEP047 requires the field whenever the `recording` entity is used. The cameras are stated to be synchronized, and no file in the deposit carries per-frame timestamps or per-camera offsets.

Derivative sidecars describe every file sharing their name. For HDF5 files that is each dataset's shape and type, plus the values of the small ones such as node names. For SLEAP files it is the frame and instance counts, track names, the video they point at and the stored provenance.

## Running it

```bash
python3 code/convert_luc3d_to_bids.py \
    --input  ember-incoming/000641 \
    --output ember-standardized/000643 \
    --config code/config.yaml \
    --dataset mouse-dyad-10m
```

| Flag | Meaning |
| --- | --- |
| `--dataset` | Dataset key of `config.yaml` |
| `--overwrite` | Reconvert sessions that already have output |
| `--jobs` | Parallel sessions. One per CPU by default. |
| `--link` | `copy` (default), `hardlink` or `symlink`. How files are placed. |
| `--ffprobe` | Path to `ffprobe` |
| `--results` | Write the sessions left unconverted as `{"pending": {...}, "failed": {...}}` |

Sessions convert in parallel. Per-session memory is small, since the converter reads HDF5 shapes and metadata and never loads pose arrays or decodes video.

A session is skipped when its `scans.tsv` exists, which is written last. A MouseDyad-10M session without its 3D file is reported as pending, because that file is the only source of the animal pair. A session whose camera folders do not match its calibration file fails.

`participants.tsv` and each `sessions.tsv` are merged by key, so a run that converts only new sessions keeps the rows of earlier runs.

## Validation

BEP047 is not in a released BIDS schema, so validate `rawbids/` against the proposal branch.

```bash
deno run -A jsr:@bids/validator ember-standardized/000643/rawbids --schema <BEP047 schema.json>
```

This has not been run yet. See Q12 in [`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md).
