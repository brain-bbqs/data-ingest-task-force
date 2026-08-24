# Standards used by this repository

The pipelines stage raw lab uploads into standardized formats ahead of DANDI upload on the EMBER archive (instance `ember-dandi`, browsable at `https://dandi.emberarchive.org/dandiset/<id>`). Two standards are in use.

Contents: decision guide, NWB targets, BIDS (BEP047) targets, DANDI requirements, expected-output example shapes.

## Decision guide

The choice of standard belongs to the requester. Use this table to understand the implications of their choice, and to shape a recommendation for them to rule on when they left the choice open.

| The data is mostly | Target | Precedent |
| --- | --- | --- |
| Neural recordings (iEEG, EEG, extracellular ephys), with or without behavior | NWB | `labs/inman/`, `labs/suthana/in-lab/` |
| Mixed physiological and behavioral time series (IMU, gaze, analog sensors) | NWB | `labs/inman/` |
| Multicamera video plus pose estimation plus analog/digital sync channels | NWB, raw + processed pair | `labs/shepherd/` |
| Raw behavioral audio, video, or image recordings with no neural data | BIDS `beh` datatype per BEP047 | `labs/kemere/` |

Both are staging formats on the way to DANDI. Kemere's BIDS tree, for example, is an intermediate step toward NWB. When a dataset straddles the line, lean NWB and note the alternative in the plan so the reviewer decides.

## NWB targets

- Write with `pynwb`. Use a `neuroconv` DataInterface when one exists for the source format (shepherd uses `DeepLabCutInterface` for DLC pose files). Check for an existing interface before hand-rolling a reader.
- One `.nwb` file per session by default. Precedented variations: a `_desc-raw` / `_desc-processed` pair per session (shepherd), one file per subject-walk (inman).
- Output layout follows the DANDI convention. Assets sit directly under `sub-<label>/` with the session in the filename. Do not nest a `ses-<label>/` subfolder, dandi validation rejects that form (see the comment in `labs/inman/code/batch_convert.py`).

  ```
  <standardized>/
    sub-<subject>/
      sub-<subject>_ses-<session>_<streams>.nwb
  ```

- A stream suffix like `behavior+ecephys` in the filename describes the modalities inside (inman precedent).
- Metadata comes from the lab's `code/config.yaml`. The NWB GUIDE (https://nwb-guide.readthedocs.io/en/stable/) documents the field requirements. `labs/inman/code/config.yaml` is the house pattern, including `PROVISIONAL` markers on unconfirmed values.
- Common containers: `TimeSeries` under `acquisition` for raw streams, `ElectricalSeries` with device / electrode-group / electrode-table plumbing for neural channels, `ImageSeries` for video, pose via the `ndx-pose` extension or neuroconv's DLC interface, and `processing/behavior` modules for derived signals.

## BIDS (BEP047) targets

BEP047 covers audio, video, and image recordings of behavior in the `beh` datatype. It is still an open bids-specification pull request, so pin what you follow and note the commit reviewed, as `labs/kemere/prompts/initial.md` does.

- Specification: https://github.com/bids-standard/bids-specification/pull/2231
- Reference dataset: `beh_audio_video_recordings` in https://github.com/bids-standard/bids-examples

Load-bearing details, verified for kemere. Re-verify them against the PR's current state on each new use:

- Suffixes and extensions: `_video` (`.mp4`/`.mkv`/`.avi`), `_audiovideo` (same extensions, when an audio stream is present), `_audio` (`.wav`/`.flac`/...), `_image` (`.png`/`.jpg`).
- Entity order: `sub`, `ses`, `task`, `acq`, `run`, `recording`, `split`. Subject is required, the rest are optional. `recording-<label>` distinguishes simultaneous camera angles.
- Every media file gets a JSON sidecar with its measured properties (via `ffprobe`: codec, frame rate, frame count, duration, dimensions, pixel format, bit depth).
- Lab-specific raw parameters ride along in the sidecar under a namespaced block (kemere's `TrackingSettings`), carrying a `Description` and `SourceFile` so provenance is explicit and the block is clearly not part of BIDS itself.
- Dataset scaffolding files are required: `dataset_description.json`, `README`, `participants.tsv`/`.json`, and per-session `scans.tsv`/`.json`. The `scans.tsv` `filename` column is participant-relative, so it includes the `ses-<label>/` prefix.
- Kemere precedent for where the tree lives inside the standardized dandiset: `<standardized>/sourcedata/rawbids/`.

## DANDI requirements that apply either way

- Subject metadata must include species (Latin binomial), sex as one of `M`/`F`/`O`/`U`, and age as an ISO 8601 duration (`P30Y`, `P5W3D`) or a date of birth.
- Subject and session labels are alphanumeric. Sanitize anything derived from folder or file names (`sanitize_label` in `labs/inman/code/batch_convert.py`).
- Associated papers become `related_publications` DOI links in NWB session metadata.
- Dandiset ids are six digits. Incoming and standardized may be one shared dandiset or two separate ones. See the field reference in `dispatch/README.md`.

## Expected-output example shapes

BIDS, one session:

```
sourcedata/rawbids/
  dataset_description.json
  README
  participants.tsv
  participants.json
  sub-multi/
    ses-20260710/
      sub-multi_ses-20260710_scans.tsv
      sub-multi_ses-20260710_scans.json
      beh/
        sub-multi_ses-20260710_recording-overhead_video.mp4
        sub-multi_ses-20260710_recording-overhead_video.json
        sub-multi_ses-20260710_acq-average_recording-overhead_image.png
        sub-multi_ses-20260710_acq-average_recording-overhead_image.json
```

NWB, one session, with the internal structure outlined per file (`labs/shepherd/code/README.md` style):

```
sub-<subject>/
  sub-<subject>_ses-<session>_behavior+ecephys.nwb
    session_start_time, session_description, identifier
    general/subject                    species, sex, age, ...
    general/devices                    acquisition hardware
    general/extracellular_ephys        electrode groups + electrode table
    acquisition/
      <one TimeSeries per raw stream>
      <ElectricalSeries for neural channels>
    processing/behavior/
      <derived series>
```
