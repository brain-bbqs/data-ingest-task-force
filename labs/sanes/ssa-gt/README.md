# sanes-ssa-gt-U01DA063581-ingest

This conversion stages Sanes SSA GT multi-animal audio, video, tracking annotations, and vocalization annotations as NWB files. It uses the `ndx-multisubjects` extension to write a `SubjectsTable` with one row per tracking `track`, and `ndx-sound` for concatenated multichannel audio. Videos are concatenated with FFmpeg, and only the concatenated video written alongside the NWB file is referenced externally. It uses `ses-experiment<ID>` session labels and writes directly under the standardized dandiset root.

The incoming tree contains `experiment_<ID>/idx_<N>/` chunks and one experiment log. The converter reads the first `Started Experiment Now` timestamp from that log as the NWB session start time. Audio channels are synchronized within and continuous across chunks. Tracking CSVs contain landmark coordinates and confidence scores. Annotation times are offset by cumulative chunk audio duration. Tracking times are offset by cumulative chunk video frames, the same clock the combined video uses. Experiment-level metadata from `metadata_SSA_GT` is preserved in `code/experiment_metadata.yaml` and remains provisional.

All animal metadata other than species is currently `PROVISIONAL`; replace it before treating output as final. The existing Sanes conversion was used as the implementation precedent. This project is intentionally separate because it has annotation CSVs instead of SLEAP files.

Before writing, the converter applies NeuroConv's HDF5 backend configuration with gzip level 4 compression to NWB datasets.

Audio is read with SciPy because the source WAV files use WAVE_FORMAT_EXTENSIBLE with IEEE float samples, which Python's standard `wave` module does not support.

## Datasets

The same converter serves three datasets. Each has its own dispatch project, config, and standardized dandiset.

| Dispatch key | Incoming | Standardized | Config |
|---|---|---|---|
| `sanes/ssa-gt` | `000524` | `000606` | `code/config.yaml` |
| `sanes/big-arena-2024-12` | `000601` | `000629` | `code/config_big_arena_2024_12.yaml` |
| `sanes/big-arena-2025-03` | `000602` | `000630` | `code/config_big_arena_2025_03.yaml` |

The BIG_ARENA layouts have not been inspected yet. They are registered on the assumption that they match SSA GT (see `OPEN_QUESTIONS.md` Q6).

## Layout

```text
labs/sanes/ssa-gt/
  code/                 Converter, batch driver, and per-dataset configs
  containers/           Runtime image
  envs/                 Unpinned dependencies
  tests/                End-to-end and unit tests
  prompts/              Request history
  OPEN_QUESTIONS.md     Deferred metadata and format questions
```

## Output

```text
sub-multi/
  sub-multi_ses-experiment280_behavior.nwb
  sub-multi_ses-experiment280_video.mp4
sub-00/
  sub-00_ses-experiment280.nwb
sub-01/
  sub-01_ses-experiment280.nwb
```

Each experiment produces one `sub-multi_ses-experiment<ID>_behavior.nwb`, its concatenated `sub-multi_ses-experiment<ID>_video.mp4`, and one `sub-<NN>/sub-<NN>_ses-experiment<ID>.nwb` per track. `NN` is the track's position in sorted track order. The multisubject file contains audio, the externally referenced concatenated video, tracking data, an `ndx-multisubjects.SubjectsTable` linking the individual files by relative path, and `processing/behavior/vocalizations` as a `pynwb.event.EventsTable`. Individual files contain one track's subject metadata and tracking data.

## The environment

`envs/pyproject.toml` is unpinned apart from documented lower bounds. `pynwb>=4` is required for `EventsTable`, and `ndx-sound>=0.2.3` is the first release whose namespace loads under current HDMF. `containers/sanes-ssa-gt.Dockerfile` resolves it at build time, adds FFmpeg, and the image digest is the reproducibility lock.

## Run it

From the repository root:

```bash
docker run --rm -v "$PWD":/work -w /work \
    ghcr.io/brain-bbqs/sanes-ssa-gt-u01da063581-ingest:latest \
    python labs/sanes/ssa-gt/code/batch_convert.py \
        --input path/to/000524/sourcedata/raw/ssa_gt_data --output path/to/000606 \
        --config labs/sanes/ssa-gt/code/config.yaml
```

Swap the input, output, and `--config` for a BIG_ARENA dataset.

## Tests

The suite synthesizes a two-chunk experiment, runs the batch driver over it, and checks the output read back with PyNWB. FFmpeg must be on `PATH`.

```bash
pip install "./labs/sanes/ssa-gt/envs[test]"
python -m pytest labs/sanes/ssa-gt/tests -q
```

## Known validation findings

`dandi validate` on a synthetic conversion reports no layout errors. It still reports these:

- `check_subject_age` on every track file while `age` is `PROVISIONAL` (Q1).
- `check_subject_exists` on the multisubject file, since `ndx-multisubjects` replaces `Subject` with `SubjectsTable`.
- A pynwb validator error looking up `NdxMultiSubjectsNWBFile` in the `ndx-sound` namespace, and an nwbinspector crash in `check_image_series_external_file_valid` on the `NWBFile` subclass. Both are upstream tooling limits with more than one extension or a subclassed `NWBFile`. The file's own namespace attributes are correct.
