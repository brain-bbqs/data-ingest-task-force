# kemere-R34DA059514-ingest

Data ingest codebase for the Kemere lab, nested under `labs/kemere/` in the
[data-ingest-task-force](https://github.com/brain-bbqs/data-ingest-task-force)
repo (see the [top-level README](../../README.md) for how labs are organized).

It converts raw behavioral recordings into a standardized BIDS dataset
(following [BEP047](https://github.com/bids-standard/bids-specification/pull/2231),
audio/video/image recordings) under `sourcedata/rawbids`, as a staging step
toward NWB / DANDI.

## Layout

```
labs/kemere/
  code/                 Conversion code (see code/README.md)
    convert_raw_to_bids.py
  containers/           The pinned, reproducible runtime (kemere.Dockerfile)
  envs/                 Loose environment declaration + pinned Python version
  tests/                One integration test + committed input/output fixtures
    example_raw/          mock raw input tree
    expected_output/      golden BIDS output the converter must reproduce
  README.md             This file
```

(Repository-wide tooling, e.g. ruff config, lives in `pyproject.toml` at the
repo root.)

## The environment

The Python environment is declared in `envs/pyproject.toml` and the interpreter
is pinned in `envs/.python-version` (3.13). The converter itself
(`code/convert_raw_to_bids.py`) is **standard-library only** — its one real
dependency is the external **FFmpeg** toolchain (`ffprobe`), a system package.

The declaration is intentionally *not* pinned. `containers/kemere.Dockerfile`
resolves it fresh at build time and the resulting image (by digest) is the
reproducibility lock, so there is no lockfile in the repository to keep in sync.
The image holds only the environment, not the code — the code and data are
mounted at run time, so a single image serves any revision of the converter.

## Run it — with the container (reproducible)

Commands below assume `labs/kemere/` as the working directory.

```bash
# Build locally...
docker build -t kemere-ingest -f containers/kemere.Dockerfile .

# ...or pull the image published by CI:
docker pull ghcr.io/brain-bbqs/kemere-r34da059514-ingest:latest

# Mount the repo + data and run the converter (code is supplied at run time):
docker run --rm -v "$PWD":/work -w /work \
    ghcr.io/brain-bbqs/kemere-r34da059514-ingest:latest \
    python code/convert_raw_to_bids.py \
        --raw-dir  000477/sourcedata/raw \
        --bids-dir 000477/sourcedata/rawbids \
        --species  "Ovis aries"

# The same image runs the test suite:
docker run --rm -v "$PWD":/work -w /work \
    ghcr.io/brain-bbqs/kemere-r34da059514-ingest:latest \
    python -m pytest tests/ -q
```

## Run it — locally (without the container)

Requires Python ≥ 3.10 and FFmpeg on `PATH` (`brew install ffmpeg` /
`apt install ffmpeg`).

```bash
python3 code/convert_raw_to_bids.py \
    --raw-dir sourcedata/raw --bids-dir sourcedata/rawbids --species "Ovis aries"
```

For iterating on the environment outside the container, `uv` is a convenient
option: `uv run --with-requirements envs/pyproject.toml ...`.

## Tests

A single integration test runs the converter on the committed mock input
(`tests/example_raw/`) and asserts the output matches the golden tree
(`tests/expected_output/`). `ffprobe` is provided by a small PyAV-backed shim so
the test is deterministic and needs no system FFmpeg.

```bash
pip install "./envs[test]"     # or "./envs[dev]" to regenerate fixtures
python -m pytest tests/ -q
```
