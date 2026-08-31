# sanes-R34DA059513-ingest

Data ingest codebase for the Sanes lab, nested under `labs/sanes/` in the
[data-ingest-task-force](https://github.com/brain-bbqs/data-ingest-task-force)
repo (see the [top-level README](../../README.md) for how labs are organized).

It converts multi-animal gerbil social vocal-interaction recordings into NWB
files. One session is a folder of `idx_*` recording chunks, each holding
per-channel audio, a behavioral video, SLEAP pose estimation, and vocalization
annotations. Each session now produces several NWB files: one per animal
track (holding that animal's pose data and `Subject`), plus one top-level
multi-subject NWB linking them and holding the concatenated multichannel
audio, chunk and combined-video `ImageSeries`, and a `vocalizations`
intervals table.

The conversion was originally authored by Neha Thomas (neha-thomas477). This
is the **v2** port: the lab supplied updated conversion scripts
(`concat_sanes_data.py`, `sanes_multisubject_to_nwb.py`,
`sanes_individual_subject_to_nwb.py`, `config_multisubject.yaml`) that
supersede the v1 notebook this repository originally ported
(`sanesDatatoNWB_v2.ipynb`, retired from the tree; still in git history).

## Layout

```
labs/sanes/
  code/                                Conversion code, ported from the v2 lab-supplied scripts
    concat_sanes_data.py                  v2 script: SLEAP merge/split + video concat, committed verbatim
    sanes_multisubject_to_nwb.py          v2 script: top-level multi-subject NWB, committed verbatim
    sanes_individual_subject_to_nwb.py    v2 script: provenance only, not run (see below)
    config_multisubject.yaml              v2 script's own config, committed verbatim
    _sanes_to_nwb.py                      those three scripts transcribed into callable functions
    batch_convert.py                      loops build_nwb over an incoming dandiset's
                                           sourcedata/raw/ -- what dispatch drives
    config.yaml                           the values the v2 scripts hard-coded / config_multisubject.yaml
                                           holds, reachable by _sanes_to_nwb.py (all still PROVISIONAL)
    pynaViz_ex.py                         the original v1 pynapple/pynaviz example for
                                           viewing a converted file, committed verbatim
    README.md                             this pipeline's own conversion notes
  containers/                          The pinned, reproducible runtime (sanes.Dockerfile)
  envs/                                Loose environment declaration
    pyproject.toml                        what the container resolves and installs
    original/                             the original v1 conda environment exports, kept
                                           verbatim as a record of what the v1 notebook ran in
  tests/                               Environment smoke test + unit tests (see Tests below)
  prompts/                             AI agent prompts given for this conversion
  README.md                            This file
```

(Repository-wide tooling, e.g. ruff config, lives in `pyproject.toml` at the
repo root.)

## The port

### v1 -> v2

The lab's original work was a Jupyter notebook (`sanesDatatoNWB_v2.ipynb`).
This repository first ported that notebook as-is; that v1 port is documented
in git history and no longer in the tree. The lab then supplied v2: three
plain Python scripts plus a new config, replacing the single-file
`build_nwb` approach with a three-stage pipeline (multi-subject layout via
`ndx-multisubjects`, `AcousticWaveformSeries` from `ndx-sound` instead of a
plain `TimeSeries`, `sleap_io` used directly instead of neuroconv's
`SLEAPInterface`, chunk videos concatenated into one file automatically
rather than as a manual notebook cell). Since v2 is no longer a notebook, the
"notebook, not a script" transcription precedent from `lab-scaffold` no
longer applies the same way it did for v1.

**Decision: the v1 notebook and its accompanying `code/README.md` are
retired from the tree.** They described a pipeline the lab has since
replaced; keeping a stale duplicate next to the current one would only
confuse the next reader, and git history keeps them recoverable. Every
reference to the notebook and the old `code/README.md`'s structure has been
updated. `pynaViz_ex.py` and `envs/original/` are v1 artifacts that are not
superseded by anything in v2 (v2 did not supply a new viewer script or
environment export), so they stay, still verbatim, still marked as v1
provenance.

### The v2 scripts, committed verbatim

`code/concat_sanes_data.py`, `code/sanes_multisubject_to_nwb.py`,
`code/sanes_individual_subject_to_nwb.py` and `code/config_multisubject.yaml`
are the lab's v2 files, byte-for-byte (apart from a short provenance comment
each). All four are excluded from the formatters and linters in
`.pre-commit-config.yaml` and from ruff in the root `pyproject.toml`, the
same treatment `pynaViz_ex.py` got for v1. None of them import correctly on
their own: they all do `from utils import config`, a sibling module the lab
did not supply among the four files handed over, so they are provenance, not
runnable code, exactly like `pynaViz_ex.py` expects the original author's
machine paths.

`code/_sanes_to_nwb.py` is those three scripts (all but
`sanes_individual_subject_to_nwb.py`, see below) transcribed into callable
functions, in the same order and with the same logic. What changed is only
what the scripts' own hard-coded paths and literals cannot carry as a
library: the input, output and config paths became arguments, and the
literals moved into `config.yaml`. `code/batch_convert.py` is new code
alongside the port and gets the normal formatting and linting treatment.

### `sanes_individual_subject_to_nwb.py`: provenance only

This script is a later, rougher pass that tries to attach a `Subject` to an
already-exported per-track NWB by guessing the track index from a
processing-module name (a `track[_=](\d+)` regex match against data-interface
names). Reading it closely, it has two real bugs as written: the `for
module_name, module in nwbfile.processing.items()` loop's body (the part that
actually reads `module.data_interfaces`) sits *after* the loop rather than
inside it, so `module` and the derived `subject_id` are whatever the last
processing module in the file happened to be, not necessarily the one that
was just iterated meaningfully; and the `with NWBHDF5IO(...) as io:` block
that reads and exports each file sits *outside* the `for nwb_file in
in_path.parent.glob("*.nwb")` loop that discovers files, so only the last
discovered file is ever actually opened and exported, regardless of how many
`.nwb` files exist.

**Decision: this script's intent is already subsumed by
`concat_sanes_data.py` writing `subject=` directly into each per-track NWB at
creation time** -- same effect, more correctly, and without guessing an
index from a name. It is committed as historical/exploratory provenance
only, the same treatment `pynaViz_ex.py` got for v1: excluded from
formatters and linters, not transcribed into `_sanes_to_nwb.py`, and not run
by the batch driver.

### One module, not several

**Decision: the callable port lives in one file, `_sanes_to_nwb.py`**, with
one function per pipeline stage (`write_per_track_nwbs`, `concat_video_files`,
`build_multisubject_nwb`) plus an orchestrating `build_nwb`. The three
stages share enough context (the same chunk folders, the same session
timing, the same config) that splitting them into separate importable
modules would mean threading that context across file boundaries for no
benefit; dispatch's one-file-hash contract (`script_path` in
`dispatch/projects.json`) also stays meaningful this way, since all the
logic that determines output content is still in one file.

### The one behavior-affecting fix this port makes

`sanes_multisubject_to_nwb.py` links each subject row to its per-track NWB
with three hard-coded paths: `sub-00/track_0.nwb`, `sub-01/track_1.nwb`,
`sub-02/track_2.nwb`. That does not match what `concat_sanes_data.py` (the
script that actually produces those files) writes: there is no `sub-NN/`
folder, the file lives directly under the output directory (`Split_SLPs/` in
this port), and the track name need not be `track_N` (it is whatever SLEAP
recorded, or `track_<id>` if unnamed). `_sanes_to_nwb.build_multisubject_nwb`
instead threads through the actual `(track_name, nwb_path)` pairs
`write_per_track_nwbs` returns, and links against those. This is the
straightforward path fix needed to run the port at all, not a change to what
the pipeline computes; see "Known rough edges" for the fixes made purely to
run against a modern, unbounded pynwb.

### The batch driver

`code/batch_convert.py` is what dispatch actually drives (see
`dispatch/README.md`). It loops `_sanes_to_nwb.build_nwb` over every session
folder discovered under an incoming dandiset's `sourcedata/raw/` (a session
being a folder that holds `idx_*` chunk folders; anything else there is
reported and skipped), and gives dispatch the same skip-unless-`--overwrite`
behavior the other labs have: an already-converted session (keyed on whether
its top-level `sanes_multisubject_1.nwb` exists) is left alone on an
ordinary pass, and only reconverted when `--overwrite` is passed (dispatch
does this automatically whenever `_sanes_to_nwb.py`'s hash changes).

Output is written under an `autogenerated/` subdirectory of the standardized
dandiset, because that dandiset already holds earlier, hand-made work at its
root:

```
<standardized>/
  autogenerated/
    ses-<session>/
      Split_SLPs/
        <track_name>.nwb
      combined_output.mp4
      sanes_multisubject_1.nwb
```

Unlike v1, there is no `sub-<subject>/` layer. v1 gave a whole recording one
grouped subject id and nested by it; v2 links several real subjects to one
session's files through `SubjectsTable` rows instead, so nesting by subject
no longer matches what the pipeline produces. The session label is the
session folder's sanitized name, still provisional.

Sessions are converted one at a time rather than in parallel, since
`build_nwb` reads every channel of every chunk into memory before writing.

### What a run produces

Confirmed by running the port end to end on a synthetic session (two `idx_*`
chunks, three audio channels each, short test videos, a two-track SLEAP
labels file, and annotation tables) built in a scratch directory:

```
Split_SLPs/
  track_0.nwb
  │   ├── general/subject (Subject, from config subject_0)
  │   └── processing/SLEAP_VIDEO_000_<chunk video>, SLEAP_VIDEO_001_<chunk video>
  │           (that track's pose data, one module per chunk video)
  └── track_1.nwb  (same shape, config subject_1)
combined_output.mp4
sanes_multisubject_1.nwb
├── general/subjects_table (SubjectsTable: species, subject_id, age, sex,
│                            individual_subj_link -> Split_SLPs/track_N.nwb)
├── acquisition
│   ├── Multi-channel Acoustic Data (ndx_sound.AcousticWaveformSeries,
│   │                                 samples x channels)
│   ├── External Behavioral Videos (ImageSeries, format="external",
│   │                                one entry per chunk video, starting_frame
│   │                                offset per chunk)
│   └── External Behavioral Video (Combined) (ImageSeries, format="external")
└── processing/behavior/vocalizations (TimeIntervals, offset by cumulative
                                         chunk video duration)
```

The fixture is not committed. It is guesswork about the source layout, not
lab data, so it is not a substitute for a real integration test (see Tests).
Video concatenation itself (the ffmpeg `concat:` demuxer step) could not be
exercised in this sandbox -- see Tests for exactly what was and was not
verified.

## Known rough edges

The packaging review in
[issue #20](https://github.com/brain-bbqs/data-ingest-task-force/issues/20)
covers the v1 code and is what v2 was written to address. Every claim below
was checked against v2's actual code (not copied from the v1 list), so an
item that sounds the same as before was independently re-confirmed still
true.

### Fixed by v2

- **Multi-subject layout.** v1 gave the whole recording one `Subject` plus a
  `DynamicTable` workaround. v2 uses `ndx-multisubjects`' `SubjectsTable`,
  linking each animal to its own per-track NWB. This is what issue #20 asked
  for.
- **`AcousticWaveformSeries` instead of a plain `TimeSeries`.** v1's notebook
  tried this and abandoned it over a `dandi validate` complaint about channel
  count (the comment is still in the code, uncommented, in v2 -- see below).
  v2 uses it. The audio's `unit` field also stops being mislabeled `'V'`
  (volts) as a side effect: `AcousticWaveformSeries`'s spec default is
  `'n.a.'`, which is honest about the raw WAV sample counts being unconverted,
  even though it still is not a calibrated physical unit.
- **`sleap_io` used directly, not neuroconv's `SLEAPInterface`.** As a side
  effect, each chunk's pose data lands in a module auto-named
  `SLEAP_VIDEO_<index>_<video name>`, indexed positionally rather than purely
  by filename, which removes v1's "two chunks whose videos share a filename
  abort the conversion" failure mode.
- **Combined video is part of the automated path**, not a manual one-off
  notebook cell (see `concat_video_files`).
- **The pynwb/sleap-io/neuroconv upper bounds v1 needed are mostly gone.**
  pynwb no longer carries an upper bound (see the two pynwb-compatibility
  fixes below); neuroconv no longer needs SLEAP support, so its `[sleap]`
  extra and matching bound are dropped. sleap-io keeps a bound, but a
  narrower and differently-motivated one -- see `envs/pyproject.toml`.
- **Float-seeded `starting_frame` array.** `_sanes_to_nwb.py` explicitly
  casts it to `int64` before constructing the `ImageSeries`, so HDMF no
  longer has to convert it with a warning.

### Not fixed by v2 (carried over)

- The video frame rate is a hard-coded 30 fps rather than read from the
  files, even though `ffprobe`/`get_video_info_ffprobe` already returns
  `r_frame_rate`. Lifted into `config.yaml` as a value, same as v1, but still
  not read from the data.
- The audio sampling rate is whichever rate the last `.wav` file read
  reported, assumed identical across every channel and chunk.
- Session start time is the time of conversion (`datetime.now`), unless
  `config.yaml` supplies one. It is not read from the data.
- The NWB `identifier` is still a fixed literal per file kind
  (`Sanes-Multisubject-1` for every session's top-level file,
  `Subject_<subject_id>` for every session's per-track files), not
  session-unique.
- Output is nested under `autogenerated/`, but DANDI wants `sub-<id>/` at the
  dandiset root, so every file reports `NON_DANDI_FOLDERNAME`. Dispatch
  registers this project with `upload_validation: ignore` for the same
  reason as v1; the layout question still belongs to issue #20.
- All audio is concatenated in memory before writing, so peak memory scales
  with the total audio in a session.
- SLEAP pose data still has no cross-chunk time offset. Each chunk's frames
  stay indexed against that chunk's own SLEAP `Video` object; nothing ties
  them onto the same clock the concatenated audio and combined video use, the
  same underlying issue v1 had, just carried by a different mechanism (v1 had
  a single processing module with unrelated per-chunk data; v2 has explicit
  per-video frame indices with no offset applied).
- Chunk layout is still assumed, not checked, and the annotations-file lookup
  is now *less* forgiving than v1's port: v2 hard-codes `annotations.csv`
  exactly (`read_chunk_annotations` matches that literally), unlike v1's
  `find_annotations_file` helper, which also matched the
  `channel_0_4_annotations.csv` naming seen in some chunks. That helper is
  not part of this port, since matching v2's actual (hard-coded) behavior was
  the more faithful choice. A chunk that names its table
  `channel_0_4_annotations.csv` (seen in real uploads, per v1's README)
  breaks v2 as supplied.
- There is no per-session metadata. `config.yaml`'s one `session` block and
  three `subject_N` blocks apply to every session in the dandiset.
- Every value in `config.yaml` is marked `PROVISIONAL`, same as v1.

### New in v2

- **The per-chunk video `ImageSeries` regresses v1's DANDI-upload fix.**
  v1's port copied each chunk's video next to the output NWB specifically
  because linking `external_file` back into the incoming tree fails DANDI
  upload validation (`check_image_series_external_file_valid`, since that
  tree is not there to resolve against once uploaded). v2's
  `sanes_multisubject_to_nwb.py` links a relative path back to the chunk's
  *original* location in the incoming session folder, not a copy. Ported
  as-is: `_sanes_to_nwb.build_multisubject_nwb` does the same, and will hit
  the same upload error v1 fixed unless a follow-up restores the copy step.
- **The gzip backend compression is computed but never applied.**
  `sanes_multisubject_to_nwb.py` builds a `backend_configuration` via
  `get_default_backend_configuration` and calls
  `backend_configuration.apply_global_compression(...)`, but then writes with
  a plain `NWBHDF5IO(...).write(nwbfile)`, the same as an uncompressed write
  -- `configure_and_write_nwbfile` (the function that would actually apply
  it) is imported but never called. Ported as-is, the same way v1's abandoned
  `AcousticWaveformSeries` attempt was documented rather than "fixed" into
  what was evidently intended.
- **`AcousticWaveformSeries` still triggers the validation complaint the
  notebook originally abandoned it over.** Building the file in this port
  raises `hdmf.build.warnings.IncorrectDatasetShapeBuildWarning: Shape of
  data does not match any allowed shapes in spec 'AcousticWaveformSeries'`
  for the multichannel audio, on every run. The v2 script's own comment next
  to the `AcousticWaveformSeries(...)` call still says `# got an error with
  dandi validate complaining about # channels`; that comment describes a
  live, reproduced issue, not a resolved one.
- **Two straightforward fixes were needed to run against pynwb without an
  upper bound**, both purely mechanical, not conversion-content changes:
  pynwb >=3.2 requires `num_samples` on an external-file `ImageSeries` timed
  by `rate=` (already flagged in v1's rough edges as *why* v1 bounded
  pynwb<3.2); this port supplies it, computed from the same per-chunk frame
  counts already tracked for `starting_frame`. Separately, pynwb's
  `ProcessingModule.add_container` was removed in favor of `.add`; this port
  uses `.add`.
- **sleap-io needs a narrow, load-bearing version pin**, discovered while
  porting, not merely carried over from v1's caution: no released version
  has both `sleap_io.model.matching.PATH_VIDEO_MATCHER` (added in 0.5.1, used
  to merge chunk `.slp` files by exact video path) and the old
  `sleap_io.io.nwb.write_nwb(labels, path, nwb_file_kwargs=...)` signature
  the v2 scripts call (renamed to a different `save_nwb` API from 0.6
  onward, and `sleap_io.io.nwb` stops being reachable as a bare attribute on
  0.6+ without an explicit submodule import, because of sleap-io's lazy
  loader) -- except the narrow 0.5.1-0.5.7 window. See
  `envs/pyproject.toml`.
- **`sanes_individual_subject_to_nwb.py`'s bugs**, detailed above under "The
  v2 scripts, committed verbatim". Not run by this pipeline.
- **Video-concat writes its `.ts` intermediates into the incoming session
  folder**, next to each chunk's original `.mp4` (`concat_video_files`
  matches `concat_sanes_data.py` exactly), not into the output directory.
  The incoming dandiset directory must be writable for this stage to run,
  and it briefly holds transcoded copies of the videos alongside the
  originals until they are removed at the end of the stage.
- **The four v2 scripts import a sibling `utils.config` module** (via `from
  utils import config`, for `config.load_cfg`/`config.cfg_get`) that was not
  among the four files the lab supplied, so the verbatim copies under
  `code/` cannot run standalone as committed.

## The environment

The Python environment is declared in `envs/pyproject.toml`. The interpreter
version (3.13) is pinned by `containers/sanes.Dockerfile`'s base image and by
the CI test job, not by a file in `envs/`. Dependencies are numpy, pandas,
scipy, natsort, python-dateutil, PyYAML, tqdm, hdmf, pynwb (no longer upper
bounded, see rough edges), sleap-io (bounded `>=0.5.1,<0.5.8`, for reasons
specific to v2, see the file's own comment), neuroconv (for
`get_default_backend_configuration`/`configure_and_write_nwbfile`, no longer
needing its `[sleap]` extra), ndx-sound, ndx-multisubjects, and
ffmpeg-python. The one system-level dependency is FFmpeg, whose `ffprobe`
the converter shells out to for video duration and frame count, and whose
`ffmpeg` binary the converter also shells out to (via `ffmpeg-python`) to
concatenate chunk videos.

Otherwise the declaration is *not* pinned. `containers/sanes.Dockerfile`
resolves it fresh at build time and the resulting image (by digest) is the
reproducibility lock, so there is no lockfile in the repository to keep in
sync. The image holds only the environment, not the code. The code and data
are mounted at run time, so a single image serves any revision of the
converter.

`envs/original/` holds the two conda environment exports the v1 notebook ran
in (`nwb_neuroconv_sleap.yaml` for the conversion, `pynapple.yaml` for the
viewer). They are provenance, not build inputs; the v2 scripts did not come
with an environment export of their own.

## Run it — with the container (reproducible)

Commands below assume the repository root as the working directory.

```bash
# Build locally...
docker build -t sanes-ingest -f labs/sanes/containers/sanes.Dockerfile labs/sanes

# ...or pull the image published by CI:
docker pull ghcr.io/brain-bbqs/sanes-r34da059513-ingest:latest

# Mount the repo + data and run the converter on one session folder
# (code is supplied at run time):
docker run --rm -v "$PWD":/work -w /work \
    ghcr.io/brain-bbqs/sanes-r34da059513-ingest:latest \
    python labs/sanes/code/_sanes_to_nwb.py \
        --input path/to/session --out path/to/out/dir \
        --config labs/sanes/code/config.yaml

# ...or run the batch driver over a whole incoming dandiset (what dispatch does):
docker run --rm -v "$PWD":/work -w /work \
    ghcr.io/brain-bbqs/sanes-r34da059513-ingest:latest \
    python labs/sanes/code/batch_convert.py \
        --input path/to/incoming/000522 --output path/to/standardized/000523 \
        --config labs/sanes/code/config.yaml

# The same image runs the test suite:
docker run --rm -v "$PWD":/work -w /work \
    ghcr.io/brain-bbqs/sanes-r34da059513-ingest:latest \
    python -m pytest labs/sanes/tests/ -q
```

## Run it — locally (without the container)

Requires Python ≥ 3.10 and FFmpeg on `PATH`. From the repository root:

```bash
pip install "./labs/sanes/envs"
python3 labs/sanes/code/_sanes_to_nwb.py \
    --input path/to/session --out path/to/out/dir \
    --config labs/sanes/code/config.yaml

# ...or the batch driver:
python3 labs/sanes/code/batch_convert.py \
    --input path/to/incoming/000522 --output path/to/standardized/000523 \
    --config labs/sanes/code/config.yaml
```

The input folder is one session, holding `idx_*` chunk folders. Each chunk
holds one `.wav` per audio channel (files with `multichannel` in the name
are skipped), one `.mp4`, at least one `.slp`, and one `annotations.csv`
(the exact name, see "Known rough edges" above).

## Tests

There is no end-to-end integration test yet. Writing one means committing
example audio, video, SLEAP and annotation fixtures, and the only ones
available are guesses at the source layout rather than lab data. A real one
belongs with the follow-up that takes ownership of the port, once a session
from the incoming dandiset can be used as the model.

What is here is an environment smoke test, plus unit tests for the pure
helpers in `_sanes_to_nwb.py` (chunk discovery, annotation-offset math,
start-time parsing) and for `batch_convert.py`'s own logic (session
discovery, the `autogenerated/` output layout, and the skip/overwrite
bookkeeping) with `build_nwb` stubbed out. The smoke test asserts `ffprobe`
is on `PATH` and that both CLIs parse, which only happens once every
third-party import resolves. That is enough to gate the published container
image on the environment declaration actually being complete.

```bash
pip install "./labs/sanes/envs[test]"
python -m pytest labs/sanes/tests/ -q
```

### What was validated building this port

A synthetic session (two `idx_*` chunks, three audio channels each, short
test videos, a two-track SLEAP labels file with predicted instances, and
annotation tables) was built by hand in a scratch directory and run through
`_sanes_to_nwb.py`'s stage 1 (`merge_chunk_sleap_labels`,
`split_labels_by_track`, `write_per_track_nwbs`) and stage 3
(`build_multisubject_nwb`), and the resulting NWB files were read back with
`pynwb` and checked: the per-track `Subject`s, the `SubjectsTable`'s links to
the actual per-track NWB paths, the concatenated audio shape, the
vocalization offsets, and the `ImageSeries` frame counts all matched what the
inputs should produce. `batch_convert.convert_batch` was also run end to end
over that fixture (session discovery, output layout, skip/overwrite).

Stage 2 (`concat_video_files`, the ffmpeg `concat:` demuxer step) could not
be exercised: the sandbox this port was built in has no system FFmpeg
install and no working package-manager mirror to install one, so testing
substituted a statically-built `ffmpeg` binary (via the `imageio-ffmpeg`
PyPI package) and a small PyAV-backed `ffprobe` shim for `get_video_info_ffprobe`.
The individual per-chunk `.mp4` -> `.ts` transcode step ran correctly under
that substitute, but the final `concat:ts1|ts2` step segfaulted inside that
specific static build regardless of input size, reproduced identically
outside Python via the bare `ffmpeg` CLI. That looks like a bug in the
substitute binary this sandbox could reach, not in `concat_video_files`
itself (the call is a direct, minimally-adapted port of
`concat_sanes_data.concat_video_files`), but it means the concat step itself
is unverified here. It should be exercised against a real FFmpeg install
(e.g. inside `containers/sanes.Dockerfile`, which does have one) before
trusting it end to end.
