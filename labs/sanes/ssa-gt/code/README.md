# SSA GT converter

`batch_convert.py` discovers `experiment_*` directories directly under `--input` or one folder below it. It writes one multisubject NWB, one concatenated video, and one individual NWB per tracking track. Experiments are converted serially. For experiment 280 the output is:

```text
sub-multi/sub-multi_ses-experiment280_behavior.nwb
sub-multi/sub-multi_ses-experiment280_video.mp4
sub-00/sub-00_ses-experiment280.nwb
sub-01/sub-01_ses-experiment280.nwb
```

The experiment log's first `Started Experiment Now` entry supplies `session_start_time`. `idx_*` directories are sorted numerically. WAV channels are copied one at a time into a temporary disk-backed array next to the output, which preserves the source sample dtype and is removed after writing. Videos are concatenated with FFmpeg and only the standardized concatenated video is referenced externally by the multisubject NWB. Annotation CSV timestamps receive the cumulative chunk audio duration as offset and are written with `pynwb.event.EventsTable.add_event`, using onset timestamps and durations plus label and channel columns. Incomplete annotation rows without start or stop times are reported and skipped. Tracking `frame_idx` values are converted to seconds on the concatenated video clock, offset by the frame count of earlier chunks. Missing tracking coordinates are represented as `NaN`. Tracking CSVs populate both the multisubject behavior module and the linked individual track NWBs.

`config.yaml` is the SSA GT dataset config. `config_big_arena_2024_12.yaml` and `config_big_arena_2025_03.yaml` configure the BIG_ARENA datasets. `session.dataset` prefixes every NWB identifier. The optional `experiment_metadata` key names a per-experiment metadata file next to the config. Only SSA GT has one.

Run from the repository root:

```bash
python3 labs/sanes/ssa-gt/code/batch_convert.py \
  --input /path/to/000524/sourcedata/raw/ssa_gt_data \
  --output /path/to/000606 \
  --config labs/sanes/ssa-gt/code/config.yaml
```
