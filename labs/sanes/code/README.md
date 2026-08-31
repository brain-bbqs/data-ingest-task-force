# `code/`

This is the v2 Sanes gerbil multi-animal vocal-interaction pipeline. See
`../README.md` for the full picture (layout, the port philosophy, known rough
edges); this file documents `code/` on its own.

## What it does

One session is a folder of `idx_*` recording chunks, each holding per-channel
audio, a behavioral video, SLEAP pose estimation, and vocalization
annotations. `_sanes_to_nwb.build_nwb` runs three stages over one session:

1. **Per-track NWBs.** Every chunk's `.slp` file is merged into one SLEAP
   `Labels` object (matching frames by exact video path), split by animal
   track, and each track is written as its own NWB under `Split_SLPs/`,
   carrying that track's pose data and a `pynwb.file.Subject` built from
   `config.yaml`.
2. **Combined video.** Every chunk's `.mp4` is concatenated into one
   `combined_output.mp4` via ffmpeg.
3. **Multi-subject session NWB.** The top-level `sanes_multisubject_1.nwb`
   uses `ndx-multisubjects` to link each subject row to its stage-1 per-track
   NWB, and holds the concatenated multichannel audio as an
   `ndx_sound.AcousticWaveformSeries`, one `ImageSeries` per chunk video plus
   one for the combined video, and a `vocalizations` `TimeIntervals` table.

`batch_convert.py` is what dispatch runs. It loops `build_nwb` over every
session folder discovered under an incoming dandiset's `sourcedata/raw/`.

## Source-to-output mapping

| Source | Output |
| --- | --- |
| `idx_*/*.slp` (merged across chunks, split by track) | `Split_SLPs/<track_name>.nwb` (pose data) + `.slp` |
| `idx_*/*.slp` track's animal identity | `Split_SLPs/<track_name>.nwb`'s `general/subject`, and the linked row in `sanes_multisubject_1.nwb`'s `SubjectsTable` |
| `idx_*/*.mp4` (concatenated) | `combined_output.mp4`, referenced by `sanes_multisubject_1.nwb`'s `External Behavioral Video (Combined)` `ImageSeries` |
| `idx_*/*.mp4` (each chunk, individually) | `sanes_multisubject_1.nwb`'s `External Behavioral Videos` `ImageSeries`, one external-file entry per chunk |
| `idx_*/*.wav` (per channel, concatenated across chunks) | `sanes_multisubject_1.nwb`'s `Multi-channel Acoustic Data` (`ndx_sound.AcousticWaveformSeries`) |
| `idx_*/annotations.csv` (offset by cumulative video duration, concatenated) | `sanes_multisubject_1.nwb`'s `behavior/vocalizations` `TimeIntervals` |

## Input layout

```
<session>/
  idx_0/
    *.wav             one file per audio channel ("multichannel" ones skipped)
    *.mp4              the behavioral video for this chunk
    *.slp              SLEAP pose estimation (a chunk may hold more than one)
    annotations.csv    vocalization annotations (start_seconds, stop_seconds, name)
  idx_1/
    ...
```

## Output layout

```
Split_SLPs/
  <track_name>.slp
  <track_name>.nwb        one per animal track, each with its own Subject
combined_output.mp4
sanes_multisubject_1.nwb  links every track NWB via SubjectsTable
```

See `../README.md`'s "What a run produces" for the confirmed NWB internal
structure.

## Run it by hand

```bash
python3 code/_sanes_to_nwb.py --input path/to/session --out path/to/out/dir --config code/config.yaml
```

`--out` is a directory now (v1 took a single output `.nwb` file path), since
v2 produces several files per session.

## Naming decisions, and where each lives

- Stage 1 (per-track NWBs + `.slp` splitting): `merge_chunk_sleap_labels`,
  `split_labels_by_track`, `write_per_track_nwbs`.
- Stage 2 (video concatenation): `concat_video_files`.
- Stage 3 (top-level session NWB): `build_multisubject_nwb`.
- `build_nwb` orchestrates all three for one session; `batch_convert.py`
  loops it over a whole incoming dandiset.

Sessions are converted one at a time, not in parallel, since `build_nwb`
reads every channel of every chunk into memory before writing (matching v1,
see `../README.md`).

## Verbatim provenance

`sanes_multisubject_to_nwb.py`, `sanes_individual_subject_to_nwb.py`,
`concat_sanes_data.py` and `config_multisubject.yaml` are the v2 scripts as
supplied by the lab, committed byte-for-byte (apart from a short provenance
comment each). `pynaViz_ex.py` is the original pynapple/pynaviz viewer
example from v1, also verbatim. None of the four v2 files are run by this
pipeline or the batch driver; `_sanes_to_nwb.py` and `batch_convert.py` are
what actually runs, and are new code with normal linting and formatting. See
`../README.md` for the full reasoning on each, especially why
`sanes_individual_subject_to_nwb.py` is provenance only.
