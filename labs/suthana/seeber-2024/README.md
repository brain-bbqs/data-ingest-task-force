# suthana-seeber-2024-r61mh135106-ingest

Data ingest codebase for the Suthana lab's second project, nested under
`labs/suthana/seeber-2024/` in the
[data-ingest-task-force](https://github.com/brain-bbqs/data-ingest-task-force)
repo (see the [top-level README](../../../README.md) for how labs are
organized, and `labs/suthana/in-lab/README.md` for the lab's first project).

It builds one group-level `NdxMultiSubjectsNWBFile` from the derived data
released alongside Seeber et al. (2024/2025), "Human neural dynamics of
real-world and imagined navigation". The source `.mat` files hold per-figure
analysis outputs (route models, wavelet power, reconstruction errors, ...),
not raw per-session recordings, which is why this is a separate project from
`labs/suthana/in-lab/` even though it shares the same five de-identified
subjects (`S1`..`S5`).

## Layout

```
labs/suthana/seeber-2024/
  code/
    seeber_2024_group_subject_to_nwb.py   the converter, ported verbatim
  containers/    The pinned, reproducible runtime (suthana-seeber-2024.Dockerfile)
  envs/          Loose environment declaration + pinned Python version
  tests/         Environment smoke test (see Tests below)
  prompts/       AI agent prompts given for this conversion
  README.md      This file
```

(Repository-wide tooling, e.g. ruff config, lives in `pyproject.toml` at the
repo root.)

## The port is verbatim, and still in progress

`code/seeber_2024_group_subject_to_nwb.py` was originally authored by Neha
Thomas and is ported here verbatim as provenance, apart from a provenance
note at the top of the file, its two hardcoded local paths (`folder` and
`saveNWBFolder`) becoming `--input`/`--output` CLI arguments, and the removal
of five unused imports. It is excluded from the formatters and linters in
`.pre-commit-config.yaml` and from ruff in the root `pyproject.toml`. A
follow-up should take ownership of it: the metadata it writes (subject rows,
electrode table) is still hardcoded from the original script rather than
driven by a `config.yaml`, and it processes one `--input` folder per
invocation rather than discovering sessions itself, so it has no
`batch_convert.py` of its own (dispatch runs it directly -- see
`dispatch/projects.json`).

### Known rough edges

- No `config.yaml`: subject and electrode metadata come from the original
  script's own hardcoded values, not from a reviewed metadata file.
- No integration test: the ported script writes one group NWB file from real
  Zenodo-released `.mat` data, and there is no small synthetic fixture for it
  yet (see Tests below).

## Running it with the container

The container is this project's pinned, reproducible runtime -- see
`containers/suthana-seeber-2024.Dockerfile`.

```bash
docker build -f labs/suthana/seeber-2024/containers/suthana-seeber-2024.Dockerfile \
  -t suthana-seeber-2024-r61mh135106-ingest labs/suthana/seeber-2024

docker run --rm \
  -v "$(pwd)/labs/suthana/seeber-2024/code:/code" \
  -v /path/to/Seeber_etal_2024_data_code:/input \
  -v /path/to/output:/output \
  suthana-seeber-2024-r61mh135106-ingest \
  python /code/seeber_2024_group_subject_to_nwb.py --input /input --output /output
```

`dispatch/dispatch.py` runs this same image automatically (its
`container_image` is registered in `dispatch/projects.json`), bind-mounting
the incoming dandiset's `sourcedata/raw/Seeber_etal_2024_data_code/` in as
`--input` and the standardized dandiset's
`sourcedata/nwb/Seeber_etal_2024_data_code/` as `--output`.

## Running it locally without the container

```bash
pip install -e labs/suthana/seeber-2024/envs[test]
python labs/suthana/seeber-2024/code/seeber_2024_group_subject_to_nwb.py \
  --input /path/to/Seeber_etal_2024_data_code \
  --output /path/to/output
```

## Tests

Only an environment smoke test exists so far (`tests/test_smoke.py`): it
checks that every third-party import the converter needs resolves and that
its CLI parses. That is what gates the published container image. A real
integration test, with a small committed `.mat` fixture and an expected
output NWB, belongs with the follow-up that finishes this project's scaffold.

```bash
pip install -e labs/suthana/seeber-2024/envs[test]
python -m pytest labs/suthana/seeber-2024/tests -q
```
