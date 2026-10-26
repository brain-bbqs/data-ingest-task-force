# sanes-ssa-gt-U01DA063581-ingest

This conversion stages Sanes SSA GT multi-animal audio, video, tracking annotations, and vocalization annotations as NWB files. It uses the `ndx-multisubjects` extension to write a `SubjectsTable` with one row per tracking `track`, and `ndx-sound` for concatenated multichannel audio. Videos are concatenated with FFmpeg, and only the concatenated video written alongside the NWB file is referenced externally. It uses `ses-experiment<ID>` session labels and writes directly under the standardized dandiset root.

The incoming tree contains `experiment_<ID>/idx_<N>/` chunks and one experiment log. The converter reads the first `Started Experiment Now` timestamp from that log as the NWB session start time. Audio channels are synchronized within and continuous across chunks. Tracking CSVs contain landmark coordinates and confidence scores. Annotation times are offset by cumulative chunk duration. Experiment-level metadata from `metadata_SSA_GT` is preserved in `code/experiment_metadata.yaml` and remains provisional.

All animal metadata other than species is currently `PROVISIONAL`; replace it before treating output as final. The existing Sanes conversion was used as the implementation precedent. This project is intentionally separate because it has annotation CSVs instead of SLEAP files.

The NWB environment pins `pynwb==3.0.0`, `hdmf==4.0.0`, and `ndx-sound==0.2.2`. These pins are required because newer HDMF releases are incompatible with the `ndx-sound` namespace schema used by this conversion.

Before writing, the converter applies NeuroConv's HDF5 backend configuration with gzip level 4 compression to NWB datasets.

Audio is read with SciPy because the source WAV files use WAVE_FORMAT_EXTENSIBLE with IEEE float samples, which Python's standard `wave` module does not support.

## Layout

```text
labs/sanes/ssa-gt/
  code/                 Converter and metadata
  containers/           Runtime image
  envs/                 Unpinned dependencies
  tests/                Unit tests
  prompts/              Request history
  OPEN_QUESTIONS.md     Deferred metadata and format questions
```

## Output

```text
sub-multi/
  sub-multi_ses-experiment280_behavior.nwb
```

Each experiment produces one `sub-multi_ses-experiment<ID>_behavior.nwb`, one `sub-XX_ses-experiment<ID>.nwb` per track, and `combined_behavior.mp4`. The multisubject file contains audio, the externally referenced concatenated video, tracking data, an `ndx-multisubjects.SubjectsTable` linking the individual files, and `processing/behavior/vocalizations` as `BehavioralEvents`. Individual files contain one track's subject metadata and tracking data.

## Tests

```bash
pip install "./labs/sanes/ssa-gt/envs[test]"
python -m pytest labs/sanes/ssa-gt/tests -q
```
