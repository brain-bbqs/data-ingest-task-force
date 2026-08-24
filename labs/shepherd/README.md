# shepherd-R34DA059723-ingest

Data ingest codebase for the Shepherd lab, nested under `labs/shepherd/` in the
[data-ingest-task-force](https://github.com/brain-bbqs/data-ingest-task-force)
repo (see the [top-level README](../../README.md) for how labs are organized).

It converts multicamera recordings of rat feeding behavior into NWB files. One
session produces two NWB files. A raw one holding the 50 kHz analog (thermistor,
sound) and digital (TTL camera exposure, trigger) channels, and a processed one
holding one `ImageSeries` per camera angle plus the DeepLabCut pose estimation.
See `code/README.md` for the input data layout and the target NWB structure.

The conversion scripts were originally authored by Grace Bezold and are ported
here verbatim. Improvements are planned as a separate follow-up.

## Layout

```
labs/shepherd/
  code/                 Conversion code, ported from the original work
    shepherd_to_nwb.py    one session folder -> raw + processed NWB files
    batch_convert.py       loops shepherd_to_nwb.build_nwb over an incoming
                            dandiset's sourcedata/raw/sessions/ -- what
                            dispatch drives
    config.yaml            metadata template consumed by the converter
    README.md               the original conversion notes (data layout, NWB tree)
  containers/           The pinned, reproducible runtime (shepherd.Dockerfile)
  envs/                 Loose environment declaration + pinned Python version
  tests/                Environment smoke test + batch_convert unit tests (see Tests below)
  prompts/              AI agent prompts given for this conversion
  README.md             This file
```

(Repository-wide tooling, e.g. ruff config, lives in `pyproject.toml` at the
repo root.)

## The port is verbatim

Unlike `labs/inman/`, `shepherd_to_nwb.py` and `config.yaml` were not
reformatted or lint-fixed on the way in. They are byte-for-byte the original
work apart from a provenance note at the top of each file. To keep it that
way, both are excluded from the formatters and linters in
`.pre-commit-config.yaml` and from ruff in the root `pyproject.toml`.
`batch_convert.py` (below) is new code alongside them and gets the normal
treatment. A follow-up that takes ownership of the ported files should drop
their exclusions in the same change.

### The batch driver

`code/batch_convert.py` is what dispatch actually drives (see
`dispatch/README.md`). It loops `shepherd_to_nwb.build_nwb` over every session
folder discovered under an incoming dandiset's `sourcedata/raw/sessions/`
(nested one level below `sourcedata/raw/` because that directory currently
holds data in a different, pre-existing shape this converter cannot read;
see the rough edge below), without editing `shepherd_to_nwb.py` itself, and
gives dispatch the same
skip-unless-`--overwrite` behavior the other three labs already have: an
already-converted session (both its `_desc-raw.nwb` and `_desc-processed.nwb`
present) is left alone on an ordinary pass, and only fully reconverted when
`--overwrite` is passed (dispatch does this automatically whenever
`shepherd_to_nwb.py`'s hash changes).

It does *not* fix the rough edges below. In particular, there is still no real
per-session metadata: every session gets `config.yaml`'s one global
`session_start_time` and one global set of subject fields (species/age/sex),
and subject identity is a placeholder (a session folder's sanitized name,
session number fixed at `1`) because no real Shepherd session-folder naming
convention is established yet. Sessions are converted one at a time rather
than in parallel, since the video-decode rough edge below means concurrent
sessions would multiply memory pressure rather than just save time.

### Known rough edges

These are all present in the original and were left alone. They are listed here
so the follow-up has a starting point, and so nobody treats the current output as
correct.

- Institution never reaches the NWB file. `config.yaml` spells the key
  `instiution` and the script reads `instituition`, so the lookup falls through
  to its default and the field is silently dropped.
- `--out` is used as a *stem*: the script appends `_desc-raw.nwb` and
  `_desc-processed.nwb` to it. The default value already ends in `.nwb`, so the
  default run writes `sub-XYZ_ses-1.nwb_desc-raw.nwb`. Pass `--out` explicitly,
  without the extension. (`batch_convert.py` always does.)
- Output directories are not created. The parent of `--out` must already exist.
  (`batch_convert.py` creates it before calling in.)
- `--session` is declared `type=int`, while the usage example in
  `code/README.md` passes `--session ABC`.
- The example `config.yaml` values are placeholders (subject 42, *Homo sapiens*,
  descriptions saying mice) and `deep-lab-cut.config` points at an
  `example_data/` path that is not in this repository. Real lab metadata and a
  real DLC config path are needed before the standardized output is final.
- Analog and digital samples are cast to `int16` while `config.yaml` declares
  their unit as volts, so the stored values are counts, not volts.
- Every video is fully decoded into memory (`np.array(frames)`) before being
  written, so peak memory scales with the total footage in a session.
- Video start time is derived from the first zero in row 0 of the first digital
  file, which assumes the TTL camera exposure channel is that row and that the
  video starts when the digital acquisition does.
- There is no established naming convention yet for real session folders under
  `sourcedata/raw/sessions/`, so `batch_convert.py` falls back to the folder's
  own name as the subject label and a fixed session number. Real per-session
  metadata (start time, subject fields) needs a real convention to key off of.
- The dandiset currently registered for Shepherd (`000528`) holds
  `sourcedata/raw/000300/sub-*/...` (`.avi` videos alongside already-built
  `.nwb` files), not the `digital`/`analog`/`videos`/`pose_estimation` layout
  this converter expects. That data predates this driver and is not real
  input for it, so discovery is nested one level deeper, under
  `sourcedata/raw/sessions/`, which is empty for now. Real Shepherd sessions
  need to be uploaded there before this project converts anything.

## The environment

The Python environment is declared in `envs/pyproject.toml`. The interpreter
version (3.13) is pinned by `containers/shepherd.Dockerfile`'s base image and
by the CI test job, not by a file in `envs/`. Most dependencies are Python
packages (numpy, pynwb, hdmf, neuroconv with its `deeplabcut` extra, opencv,
natsort, PyYAML). The one system-level dependency is FFmpeg, whose `ffprobe`
the converter shells out to for video duration and frame count.

The declaration is intentionally *not* pinned. `containers/shepherd.Dockerfile`
resolves it fresh at build time and the resulting image (by digest) is the
reproducibility lock, so there is no lockfile in the repository to keep in sync.
The image holds only the environment, not the code. The code and data are mounted
at run time, so a single image serves any revision of the converter.

## Run it — with the container (reproducible)

Commands below assume the repository root as the working directory.

```bash
# Build locally...
docker build -t shepherd-ingest -f labs/shepherd/containers/shepherd.Dockerfile labs/shepherd

# ...or pull the image published by CI:
docker pull ghcr.io/brain-bbqs/shepherd-r34da059723-ingest:latest

# Mount the repo + data and run the converter on one session folder
# (code is supplied at run time):
docker run --rm -v "$PWD":/work -w /work \
    ghcr.io/brain-bbqs/shepherd-r34da059723-ingest:latest \
    python labs/shepherd/code/shepherd_to_nwb.py \
        --input_folder path/to/session --subject XYZ --session 1 \
        --config labs/shepherd/code/config.yaml \
        --out path/to/out/sub-XYZ_ses-1

# ...or run the batch driver over a whole incoming dandiset (what dispatch does):
docker run --rm -v "$PWD":/work -w /work \
    ghcr.io/brain-bbqs/shepherd-r34da059723-ingest:latest \
    python labs/shepherd/code/batch_convert.py \
        --input path/to/incoming/000528 --output path/to/standardized/000529 \
        --config labs/shepherd/code/config.yaml

# The same image runs the test suite:
docker run --rm -v "$PWD":/work -w /work \
    ghcr.io/brain-bbqs/shepherd-r34da059723-ingest:latest \
    python -m pytest labs/shepherd/tests/ -q
```

## Run it — locally (without the container)

Requires Python ≥ 3.10 and FFmpeg on `PATH`. From the repository root:

```bash
pip install "./labs/shepherd/envs"
python3 labs/shepherd/code/shepherd_to_nwb.py \
    --input_folder path/to/session --subject XYZ --session 1 \
    --config labs/shepherd/code/config.yaml \
    --out path/to/out/sub-XYZ_ses-1

# ...or the batch driver:
python3 labs/shepherd/code/batch_convert.py \
    --input path/to/incoming/000528 --output path/to/standardized/000529 \
    --config labs/shepherd/code/config.yaml
```

The input folder is one session, laid out with `digital/`, `analog/`, `videos/`,
and `pose_estimation/` subfolders. See `code/README.md`.

## Tests

There is no end-to-end integration test yet. Writing one means running
`shepherd_to_nwb.build_nwb` for real, and the rough edges above mean that
cannot happen without editing the ported code, which this change deliberately
does not do. It belongs with the follow-up that fixes them.

What is here is an environment smoke test, plus unit tests for
`batch_convert.py`'s own logic (session discovery, output paths, and the
skip/overwrite bookkeeping) with `build_nwb` stubbed out. The smoke test
asserts `ffprobe` is on `PATH` and that the CLI parses, which only happens
once every third-party import in the converter resolves. That is enough to
gate the published container image on the environment declaration actually
being complete.

```bash
pip install "./labs/shepherd/envs[test]"
python -m pytest labs/shepherd/tests/ -q
```
