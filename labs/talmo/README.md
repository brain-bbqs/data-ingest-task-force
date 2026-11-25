# talmo-U01DA063581-ingest

Data ingest codebase for the Talmo lab, nested under `labs/talmo/` in the [data-ingest-task-force](https://github.com/brain-bbqs/data-ingest-task-force) repo (see the [top-level README](../../README.md) for how labs are organized).

It converts the two LUC3D collections of dandiset `000641` into BIDS study datasets. Videos become a raw BIDS dataset following [BEP047](https://github.com/bids-standard/bids-specification/pull/2231). The SLEAP 2D pose, triangulated 3D pose, calibration and models go under `derivatives/` in their native formats. A conversion of the pose to NWB is left for later.

| Dataset key | Collection | Incoming | Standardized |
| --- | --- | --- | --- |
| `mouse-dyad-10m` | MouseDyad-10M, male-female mouse pairs, 5 cameras, 56 sessions | `000641` | `000643` |
| `slap-2m` | SLAP-2M, 1 to 4 mice in an enriched arena, 8 cameras, 74 sessions | `000641` | `000642` |

The data accompany the preprint "LUC3D: Multi-animal 3D pose tracking in the browser" ([doi:10.64898/2026.11.17.767188](https://doi.org/10.64898/2026.11.17.767188)).

## Layout

```
labs/talmo/
  code/                 Conversion code (see code/README.md)
    convert_luc3d_to_bids.py
    config.yaml           per-dataset metadata
  containers/           The pinned, reproducible runtime (talmo.Dockerfile)
  envs/                 Loose environment declaration
  tests/                Integration tests + committed fixtures
    example_raw/          generated mock of dandiset 000641
    expected_output/      golden study trees the converter must reproduce
  prompts/              The request record and the conversion plan
  OPEN_QUESTIONS.md     What the conversion still depends on
  README.md             This file
```

## Provisional metadata

Values marked `PROVISIONAL` in [`code/config.yaml`](code/config.yaml) keep the conversion runnable. Replace them before treating the output as final. [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) lists each one, what it blocks, and what to ask.

The largest gaps are the animals' ages, the per-animal metadata of SLAP-2M, the author list, and confirmation of the license and recording institutions. The preprint could not be read from the build sandbox, so everything sourced beyond the deposit itself comes from the lab's public dataset cards.

## The environment

The Python environment is declared in `envs/pyproject.toml`. It needs `h5py`, `PyYAML` and `tqdm`, plus the external FFmpeg toolchain (`ffprobe`), a system package. The interpreter version (3.13) is pinned by the Dockerfile's base image and by the CI test job.

The declaration is intentionally not pinned. `containers/talmo.Dockerfile` resolves it fresh at build time, and the resulting image (by digest) is the reproducibility lock. The image holds only the environment. Code and data are mounted at run time.

## Run it with the container

Commands assume `labs/talmo/` as the working directory.

```bash
docker build -t talmo-ingest -f containers/talmo.Dockerfile .
```

```bash
docker pull ghcr.io/brain-bbqs/talmo-u01da063581-ingest:latest
```

```bash
docker run --rm -v "$PWD":/work -w /work \
    ghcr.io/brain-bbqs/talmo-u01da063581-ingest:latest \
    python code/convert_luc3d_to_bids.py \
        --input 000641 --output 000643 --dataset mouse-dyad-10m
```

```bash
docker run --rm -v "$PWD":/work -w /work \
    ghcr.io/brain-bbqs/talmo-u01da063581-ingest:latest \
    python -m pytest tests/ -q
```

## Run it locally

Requires Python 3.11 or newer and FFmpeg on `PATH`.

```bash
pip install "./envs"
```

```bash
python3 code/convert_luc3d_to_bids.py --input 000641 --output 000642 --dataset slap-2m
```

Each standardized dandiset receives a full second copy of its videos (105.5 GB for MouseDyad-10M, 188.9 GB for SLAP-2M). `--link hardlink` avoids the copy when input and output share a filesystem.

## Tests

One integration test per dataset runs the converter on `tests/example_raw/` and compares the result with `tests/expected_output/`. Further tests cover skipping converted sessions, reporting out-of-scope files, the empty-dandiset case and the identity rules. `ffprobe` is provided by a PyAV-backed shim, so no system FFmpeg is needed.

```bash
pip install "./envs[test]"
```

```bash
python -m pytest tests/ -q
```

The fixtures are generated, not lab data. `tests/generate_fixtures.py` synthesizes them from the layout of the real deposit, with fewer cameras and five-frame arrays. Rebuild them with the `dev` extra after an intended change.
