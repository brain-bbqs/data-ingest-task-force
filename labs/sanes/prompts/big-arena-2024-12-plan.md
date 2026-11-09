# Sanes Big_Arean_2024_12 conversion plan

Status: approved by the requester on 2026-11-03 with "The plan looks good". Implementation extends the existing shared converter and config. The existing registration and image are reused.

## Amendments after approval

These changes were made during implementation and review. The reviewer (CodyCBakerPhD) confirmed them in Request 7 of [the request record](big-arena-2024-12.md). The requester has not been asked to confirm them separately.

- Audio is one eight-column `AcousticWaveformSeries`, as planned. `ndx-sound` 0.2.3 allowed only one or two channels per series, so the environment now requires `ndx-sound>=0.3.0`. An interim implementation split the audio into eight mono series, which Request 7 reverted.
- Each microphone and camera gets a device whose description is marked `PROVISIONAL` until the lab supplies hardware.
- NWB has no funding field. The award is noted in the dataset config header and the lab README, and belongs in the `000629` dandiset metadata.
- Video frames are placed at their segment's manifest start plus their offset from the segment's first frame. A segment whose last frame reaches the next segment's manifest start stops conversion for a person to review.
- MP4 data streams such as timecode tracks are dropped and reported. Embedded camera audio is kept in the MP4 and reported, not converted.
- An `experiment_*` folder without a supported layout is reported as pending to dispatch, rather than failing the batch.
- This plan lives in `prompts/` rather than the lab root.

## Questions for review

1. Confirm the recording computer's timezone when available. The requester identified NYU and said "presumably East coast." Use `America/New_York` as `PROVISIONAL`, giving a candidate start of `2024-12-10T16:27:56-05:00` for this date. Neither attachment supplies an offset. Do not reuse the existing config's provisional `UTC` or treat the institution as proof of the computer's timezone.
2. Animal data is not yet available, as confirmed by the requester. Count, stable IDs, species, sex, and ages or birth dates remain open. Existing Sanes metadata suggests `Meriones unguiculatus`, but that species is `PROVISIONAL` for this collection. There are no subject identities or pose tracks in the supplied files. Do not invent a roster.
3. Packaging is confirmed by the requester: "Yes, one NWB plus five external MP4s". The single NWB contains the complete audio and all five video references.
4. Confirm experimenter, session description, acquisition hardware, microphone/channel locations, and camera identities. The requester confirmed NYU as the institution. No audio calibration is supplied. Preserve digital samples without claiming calibrated pressure or voltage.
5. Is the display name exactly `Big_Arean_2024_12`, or should it be `BIG_ARENA_2024_12`, as the existing config and registry call it? Keep the established machine key `sanes/big-arena-2024-12` unless a rename is requested.

The requester approved the mapping with these metadata gaps left open. Timezone and a real animal roster must be resolved before producing scientifically complete output. A `PROVISIONAL` value remains explicitly marked in documentation and future configuration, never silently promoted to confirmed metadata. Invalid placeholders must not reach final upload.

## Completed intake

| Field | Recorded value and source |
| --- | --- |
| Lab and PI | Sanes, Dan Sanes, supplied by requester |
| Award | `U01DA063581`, supplied by requester |
| Dataset display name | `Big_Arean_2024_12`, supplied spelling preserved |
| Codebase and layout | Extend `labs/sanes/`, which already serves this dataset. No copied sibling converter or new project directory. This input requires another source-layout reader. |
| Incoming and standardized | `000601` → `000629`, supplied by requester |
| Archive | `ember-dandi`, repository default. Archive contents have not been inspected. |
| Institution/contact | New York University (NYU), confirmed by requester follow-up. Metadata contact not supplied. |
| Science | Group behavioral audio/video in an arena. Exact task/protocol not supplied. No neural data shown. |
| Species | `Meriones unguiculatus` from existing Sanes config, `PROVISIONAL` pending confirmation for this dataset |
| Acquisition | Eight named WAV microphone channels and five named MP4 camera views. Models, rates, calibration, and physical locations unknown. |
| Papers | None, supplied by requester. `related_publications: []`. |
| Target | NWB with `ndx-multisubjects`, one continuous file per experiment, as requested |
| Example | "similar to other sanes conversion, with all continuous data in one NWB file using multisubjects for audio/video data." |
| Prior work | Shared `_sanes_to_nwb.py`, batch driver, dataset config, and original lab scripts under `labs/sanes/code/`, read locally |
| Author and reuse | Original work credited to Neha Thomas (neha-thomas477, nehatk17) in the lab README. Extend the maintained converter after approval. Keep original scripts as verbatim provenance. |
| Session boundary | `sourcedata/raw/experiment_109/` is one session. `concatenated_data_cam_mic_sync/` is its media folder. Six CSV rows are continuous segments, not six sessions. |
| Identity source | Experiment folder supplies session ID. Requester confirmed animal data is unavailable. No animal roster or within-video subject identification supplied. |
| Duration and volume | Six nominal 360-second segments, 2,160 seconds total. 48 WAVs and 30 MP4s named by metadata. File sizes, sample/frame counts, and total dataset size unknown. |
| Operational needs | FFmpeg/ffprobe, existing Sanes Python dependencies, streamed/disk-backed audio, per-camera remuxing. No media decode or conversion has been run. |

The verbatim source tree is preserved in [the request record](big-arena-2024-12.md). All filenames in that tree are mapped below. Unknown contents of `temp/` are explicitly excluded and reported.

### Evidence actually inspected

- `/Users/thoman1/Downloads/sync.csv`, all six rows, with columns `video`, `audio`, and `timestamp`. Cells contain Python-style list literals. Future parsing must use a safe literal parser with type validation, never `eval`.
- `/Users/thoman1/Downloads/README.txt`, all six synchronization descriptions. It agrees with the CSV on all 78 distinct media basenames and all timestamp boundaries.
- Existing Sanes README, code README, configs, maintained converter, batch driver, multisubject provenance script, open questions, prior prompt records, and the BIG_ARENA entries in `dispatch/projects.json` and `dispatch/sessions.json`.
- No source WAV/MP4 files, `temp/` contents, archive assets, or recording logs were inspected. Durations here are metadata claims, not measured media durations. Species and subject metadata cannot be established from these attachments.

Attachment fingerprints allow checking a later copy against the versions inspected here.

| Attachment | Bytes | SHA-256 |
| --- | --- | --- |
| `sync.csv` | 2201 | `e0260e5319e5c230382b45ad3f6f766d2f1cff6adcd2aa066a525def57b535ca` |
| `README.txt` | 2107 | `c6d08c3cd72375659661ee248f9318d5dba63345544b88d1c95c36ff45089091` |

### Implementation gaps identified during intake

The dataset was already configured and registered. These gaps were addressed in the shared converter, driver, dataset config, READMEs, and open-questions record after approval. Registration alone did not establish support for these inputs.

- Batch discovery requires `idx_*` directories and would skip this experiment, currently reporting no sessions with success. It must recognize the manifest-backed media folder and report unsupported experiments visibly.
- Chunk discovery only sees `idx_*`, and `_chunk_video` rejects more than one MP4 per chunk. The new reader must group all five cameras separately across manifest rows.
- `_session_start` reads experiment logs or a fixed config value. It does not read `sync.csv`, and this dataset config has no fallback start time.
- `SubjectsTable` is currently created only from pose-track output files. This input needs a roster-driven table independent of pose and without inventing per-animal recordings.
- The README claim that all Sanes sources have one `idx_*` layout is disproved by this supplied tree. Update that documentation when implementation lands. The config also describes tracking and annotations absent from this example.
- Open question Q6 is partly answered for `000601`: this experiment's path and timestamp source are now known. Other experiments and `000602` remain uninspected. Do not close Q6 for both datasets.

## Standard, granularity, and identity

Use `ndx_multisubjects.NdxMultiSubjectsNWBFile`, `ndx_sound.AcousticWaveformSeries`, and five `pynwb.image.ImageSeries` objects. NWB is the requester's decision. Produce exactly one NWB per `experiment_*` directory, regardless of segment count. No separate per-animal NWBs, pose, or vocalization annotation tables are planned because those source data are absent.

Retain the established Sanes naming rules. Remove non-alphanumeric characters from the experiment basename in the existing session-label function, so `experiment_109` becomes `experiment109`. Preserve the folder name as provenance. Reject label collisions within a dataset before writing. Use collective DANDI label `multi` for the file, never as an individual animal ID. Populate `SubjectsTable` with the actual roster once supplied. Sanitize animal labels in one identity helper, retain original IDs, and reject collisions rather than inventing replacements.

Use identifier `sanes-big-arena-2024-12-experiment_109`, matching the current dataset-qualified identifier convention. The output dandiset is separate from the input. Write directly under `sub-multi/`, without `autogenerated/` or a `ses-.../` directory.

## Complete source mapping

Paths below are relative to `sourcedata/raw/experiment_109/concatenated_data_cam_mic_sync/`. In every media row, `{segment}` expands to exactly `000`, `001`, `002`, `003`, `004`, and `005`, as explicitly listed in `sync.csv`. Membership and ordering come from validated manifest rows, not a recursive glob. Audio columns use numeric channel order, independent of the CSV's list order.

| Source | Fate and standardized destination |
| --- | --- |
| Parent `experiment_109/` | Metadata. Session `experiment109`, one NWB for all rows. |
| `channel_00_file_{segment}.wav` | Converted. Concatenate in time into column 0 of the `AcousticWaveformSeries` at `acquisition/Multi-channel Acoustic Data`. |
| `channel_01_file_{segment}.wav` | Converted. Concatenate in time into column 1 of the `AcousticWaveformSeries` at `acquisition/Multi-channel Acoustic Data`. |
| `channel_02_file_{segment}.wav` | Converted. Concatenate in time into column 2 of the `AcousticWaveformSeries` at `acquisition/Multi-channel Acoustic Data`. |
| `channel_03_file_{segment}.wav` | Converted. Concatenate in time into column 3 of the `AcousticWaveformSeries` at `acquisition/Multi-channel Acoustic Data`. |
| `channel_04_file_{segment}.wav` | Converted. Concatenate in time into column 4 of the `AcousticWaveformSeries` at `acquisition/Multi-channel Acoustic Data`. |
| `channel_05_file_{segment}.wav` | Converted. Concatenate in time into column 5 of the `AcousticWaveformSeries` at `acquisition/Multi-channel Acoustic Data`. |
| `channel_06_file_{segment}.wav` | Converted. Concatenate in time into column 6 of the `AcousticWaveformSeries` at `acquisition/Multi-channel Acoustic Data`. |
| `channel_07_file_{segment}.wav` | Converted. Concatenate in time into column 7 of the `AcousticWaveformSeries` at `acquisition/Multi-channel Acoustic Data`. |
| `video_center_{segment}.mp4` | Converted. Concatenate this view into `sub-multi_ses-experiment109_recording-center_video.mp4`, referenced by `acquisition/video_center`. |
| `video_gily_center_{segment}.mp4` | Converted. `sub-multi_ses-experiment109_recording-gilycenter_video.mp4`, referenced by `acquisition/video_gily_center`. |
| `video_gily_nest_{segment}.mp4` | Converted. `sub-multi_ses-experiment109_recording-gilynest_video.mp4`, referenced by `acquisition/video_gily_nest`. |
| `video_gily_underground_{segment}.mp4` | Converted. `sub-multi_ses-experiment109_recording-gilyunderground_video.mp4`, referenced by `acquisition/video_gily_underground`. |
| `video_underground_{segment}.mp4` | Converted. `sub-multi_ses-experiment109_recording-underground_video.mp4`, referenced by `acquisition/video_underground`. |
| `sync.csv` | Metadata. First timestamp supplies session start once timezone is confirmed. Every row supplies the segment interval and media associations. Preserve its original text in `scratch/source_sync_csv` and its validated associations in `intervals/source_segments`. |
| `README.txt` | Metadata. Preserve original text in `scratch/source_readme`. Cross-check against the manifest and fail on contradictory synchronization descriptions. |
| `temp/` and all descendants | Out of scope. Report excluded paths. Never recurse into them for media discovery. |
| Any unexpected or unlisted source file | Report as out of scope, pending review. A missing manifest-listed media file is an error, never an ignored file. |

The `recording-...` names distinguish five assets in this proposal. Verify DANDI organization and validation of these exact names during implementation, and update relative NWB references if organization renames them.

### Timing contract

`sync.csv` and `README.txt` describe the following nominal intervals. All times are local and timezone-naive as supplied.

| Segment | Start on 2024-12-10 | End on 2024-12-10 | Relative interval, seconds |
| --- | --- | --- | --- |
| `000` | 16:27:56 | 16:33:56 | [0, 360) |
| `001` | 16:33:56 | 16:39:56 | [360, 720) |
| `002` | 16:39:56 | 16:45:56 | [720, 1080) |
| `003` | 16:45:56 | 16:51:56 | [1080, 1440) |
| `004` | 16:51:56 | 16:57:56 | [1440, 1800) |
| `005` | 16:57:56 | 17:03:56 | [1800, 2160) |

After timezone confirmation, set timezone-aware `session_start_time` from the first row and use that instant as zero for every stream. The current working timezone is `America/New_York`, explicitly `PROVISIONAL` based on the requester's follow-up. Never infer timezone from the agent's environment or dataset name. Sort rows by parsed start timestamp, require increasing non-overlapping intervals and matching adjacent boundaries, and validate segment suffixes and camera/channel membership. Check path safety, duplicate entries, and the expected eight channels and five views in every row. Do not group simultaneous cameras sequentially on one timeline.

Read audio headers and probe each MP4 before allocating output. Require mono WAVs, equal sample counts/rates within each segment across all microphones, and compatible sample types/rates across segments. For each channel, concatenate samples in manifest order into an `(N, 8)` disk-backed array, compressing the NWB datasets with gzip level 4 as in the maintained converter. At each boundary compare cumulative sample time against the manifest offset. The manifest is only precise to whole seconds, so it cannot demonstrate subsecond synchronization. Document and justify an acceptance tolerance from actual acquisition timing precision before implementation acceptance. Report measured residuals. A conflict must stop conversion for review. Do not silently trim, pad, resample, or stretch data.

Probe each view independently for codec, dimensions, time base, presentation timestamps, frame count, frame rate, and duration. Concatenate segments only within a view, preferring lossless stream-copy remuxing when compatible. Validate the combined frame count against the sum of input frames and check frame timing at every segment boundary. Never assume 30 fps or equal rates across cameras. Use `starting_time=0` and a measured `rate` only when each camera is demonstrably regular and agrees with the shared timeline. Otherwise use explicit session-relative frame timestamps derived from presentation timestamps plus validated segment offsets. A discontinuity or disagreement requires review before calling the result continuous. Do not transcode or invent missing frames without an approved decision.

Each `ImageSeries` references exactly its own standardized MP4 by relative filename with `format="external"` and `starting_frame=[0]`. The NWB must not reference raw input paths. All referenced MP4s ship with the NWB. Inspect whether MP4s carry embedded audio. Preserve and report it if present rather than silently stripping an uninspected stream.

## Expected output for experiment_109

This is a proposed structural example, not generated or validated output.

```text
000629/
  sub-multi/
    sub-multi_ses-experiment109_behavior.nwb
    sub-multi_ses-experiment109_recording-center_video.mp4
    sub-multi_ses-experiment109_recording-gilycenter_video.mp4
    sub-multi_ses-experiment109_recording-gilynest_video.mp4
    sub-multi_ses-experiment109_recording-gilyunderground_video.mp4
    sub-multi_ses-experiment109_recording-underground_video.mp4
```

```text
sub-multi_ses-experiment109_behavior.nwb (NdxMultiSubjectsNWBFile)
  identifier: sanes-big-arena-2024-12-experiment_109
  session_id: experiment109
  session_start_time: 2024-12-10T16:27:56-05:00 (PROVISIONAL timezone)
  session_description: confirmed behavioral recording description
  general/
    lab, institution, experimenter
    related_publications: []
    devices/                         one per microphone and camera, PROVISIONAL until confirmed
    SubjectsTable/                   one row per actual animal, only when roster is supplied
      subject_id, species, sex, age (or extension-supported birth metadata)
  acquisition/
    Multi-channel Acoustic Data/     one AcousticWaveformSeries
      data: (N, 8), columns channel_00 to channel_07, preserving original digital samples
      starting_time: 0
      rate: measured audio sample rate
      unit: n.a. (fixed by ndx-sound), digital-sample meaning in description
    video_center/                    ImageSeries, relative external_file
    video_gily_center/               ImageSeries, relative external_file
    video_gily_nest/                 ImageSeries, relative external_file
    video_gily_underground/          ImageSeries, relative external_file
    video_underground/              ImageSeries, relative external_file
  intervals/
    source_segments/                 TimeIntervals, six rows
      start_time, stop_time, segment_id, audio_files, video_files
      measured sample/frame boundary information and timing residuals
  scratch/
    source_sync_csv                  original manifest text
    source_readme                    original synchronization explanation
```

Preserve the full original channel names and camera names in descriptions/provenance even when filenames use sanitized labels. This recording has no supplied pose or annotation data, so the outline has no synthetic tracks, per-animal NWBs, or vocalizations.

## Metadata and extension plan

This table is the specification for later updates to `code/config_big_arena_2024_12.yaml` and per-experiment metadata. No config is changed during planning.

| Metadata | Destination and rule |
| --- | --- |
| Award `U01DA063581` | Noted in the dataset config header and the lab README. NWB has no funding field, so it belongs in the `000629` dandiset metadata. Keep the existing shared runtime image name. |
| Dataset key and source experiment | Dataset-qualified `identifier`, `session_id`, and provenance |
| First CSV timestamp + timezone | NWB `session_start_time`, no global fallback date. `America/New_York` is `PROVISIONAL`. Candidate start `2024-12-10T16:27:56-05:00`. |
| Continuity and file associations | `intervals/source_segments`, original texts in `scratch` |
| Lab | `lab: Sanes`, confirmed by requester |
| Institution | New York University (NYU), confirmed by requester follow-up |
| Experimenter, description | NWB session metadata. `PROVISIONAL` until confirmed. Use an audio/video description for this input, not inherited claims about tracking/annotations. |
| Actual animal roster | `SubjectsTable` rows keyed by supplied stable IDs, independent of whether tracking exists |
| Species, sex, age/birth date | Per actual animal. Species `PROVISIONAL` as above. Sex only `M`, `F`, `O`, or `U`. `U` denotes unknown, not a biological inference. Age must be valid ISO 8601 duration or use supported birth metadata. Do not inherit placeholder ages. |
| Microphone channel map | Audio series description and device metadata, ordered `00`–`07`. Hardware and calibration `PROVISIONAL` |
| Camera view map | One `ImageSeries` per view, device metadata and measured timing properties. Models/locations `PROVISIONAL` |
| Papers | Empty `related_publications`, as supplied |

The maintained converter currently writes `individual_subj_link` pointing at per-track NWBs. This plan requires a self-contained roster without those files. The installed `ndx-multisubjects` 0.1.1 schema makes per-animal links optional, verified by round-trip tests of a roster without pose or per-animal NWBs. If that representation is unsupported, return the concrete constraint for review rather than inventing subjects, dangling links, or extra NWBs. Do not claim extension compatibility before testing it.

Existing Sanes documentation records DANDI `check_subject_exists` warnings for multisubject files. Validate the proposed output with PyNWB, NWB Inspector, and DANDI, record extension-specific limitations separately from missing metadata, and seek review of any unresolved upload constraint. Do not silently add `upload_validation: ignore` or a fabricated ordinary subject to make validation pass.

## Work after approval

1. Record approval and corrections verbatim in `prompts/big-arena-2024-12.md`. Resolve the metadata and storage decisions above or explicitly agree which stay `PROVISIONAL` for development.
2. Run lab-scaffold as an extension of the existing codebase. Add a manifest-backed source reader feeding shared writing logic while preserving the existing `idx_*` datasets. Centralize identity and camera-label rules. Add roster-driven subjects, segment provenance, all five video series, manifest-derived session start, and explicit error reporting.
3. Verify with small representative media fixtures covering eight channels, five distinguishable cameras, and multiple continuous segments. Check sample/frame content and boundary timing after NWB round-trip, external link resolution, roster without pose, and rejection of missing/duplicate files, timing conflicts, or malformed manifest cells. Mark generated tests `ai_generated`, parametrize failure cases, and run existing Sanes tests to check the prior datasets.
4. Run lab-register to audit the existing `sanes/big-arena-2024-12` entry, not create a duplicate. Confirm experiment discovery, invoke a dispatch dry run, and pass dispatch tests. Existing inclusion globs already cover `sourcedata/raw/experiment_109`. Batch discovery is the present gap. Update README claims and Q6 only to the extent demonstrated.
5. Run required validation and pre-commit before any eventual commit/push. Finish with lab-lessons for implementation findings.

## Lessons from intake and planning

Applied lab-lessons during planning and implementation to strengthen three checklist steps in the shared skills. Same-lab datasets need their supplied layout checked against the current reader, even when already registered. A multisubject audio/video plan must explain where subject identity comes from when pose files are absent. Reused outputs must have their proposed shapes checked against the installed extension schemas. These are factual planning checks and do not change the requester-owned standard or output-granularity defaults. Implementation and registration verification are described below. Actual lab-media conversion and final upload remain pending.

## Implementation verification

The shared converter now reads the supplied manifest layout, preserves eight continuous microphones and
five separate video views, records segment provenance and timing residuals, supports an actual roster
independently of pose, and explicitly reports missing metadata. The batch driver discovers this layout,
reports unsupported experiments as pending, and rejects colliding session labels. No real archive WAV/MP4 data has been
inspected or converted. Tests use a committed, clearly identified synthetic six-second session.

Existing registration touchpoints were audited. The same dataset config, script hash target, shared
container image, session globs, image build registration, and CI environment apply. A dispatch dry run
against the synthetic input discovers `experiment_109` and resolves `000601` to `000629`. Changes to the
shared converter trigger reprocessing of all four registered Sanes datasets, including live ones.

Final upload remains pending actual metadata and extension-validator support. The finalized verification
commands and remaining constraints are documented in `code/README.md` and `OPEN_QUESTIONS.md`. No upload
validation policy was weakened, and no data was uploaded.
