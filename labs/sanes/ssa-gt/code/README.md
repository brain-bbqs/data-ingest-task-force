# SSA GT converter

`batch_convert.py` discovers `sourcedata/raw/ssa_gt_data/experiment_*` directories and writes one multisubject NWB plus one individual NWB per tracking track. For experiment 280 the output is:

```text
sub-multi_ses-experiment280_behavior.nwb
sub-00_ses-experiment280.nwb
sub-01_ses-experiment280.nwb
combined_behavior.mp4
```

The experiment log's first `Started Experiment Now` entry supplies `session_start_time`. `idx_*` directories are sorted numerically. WAV channels are concatenated into one `ndx_sound.AcousticWaveformSeries` through a temporary disk-backed array that preserves the source sample dtype, avoiding a second full in-memory copy. Videos are concatenated with FFmpeg and only the standardized concatenated video is referenced externally by the multisubject NWB. Annotation CSV timestamps receive the same cumulative offset and are written with `pynwb.behavior.EventsTable.add_event`, using onset timestamps plus label, channel, and duration columns. Incomplete annotation rows without start or stop times are reported and skipped. Missing tracking coordinates are represented as `NaN`. Tracking CSVs populate both the multisubject behavior module and the linked individual track NWBs.

Run from the repository root:

```bash
python3 -m labs.sanes.ssa_gt.code.batch_convert \
  --input /path/to/000524 \
  --output /path/to/000606 \
  --config labs/sanes/ssa-gt/code/config.yaml
```

The output path is direct under the standardized dandiset and uses `sub-multi_ses-experiment<ID>_behavior.nwb`.
