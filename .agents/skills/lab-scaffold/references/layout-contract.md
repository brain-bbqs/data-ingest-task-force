# Layout contract, file by file

Contents: naming, `code/`, the dispatch contract for the batch driver, `config.yaml`, `code/README.md`, `envs/`, `containers/`, `tests/`, `prompts/`, the lab `README.md`.

## Naming

Names derive from the lab key, the project name when there is one, and the grant award number from intake.

| Thing | Rule | Example |
| --- | --- | --- |
| Lab directory | `labs/<lab>/`, or `labs/<lab>/<project>/` | `labs/suthana/in-lab/` |
| Ingest name | `<lab>[-<project>]-<award>-ingest` | `kemere-R34DA059514-ingest` |
| Lab README title | The ingest name, award in original case | `# shepherd-R34DA059723-ingest` |
| `envs/pyproject.toml` project name | The ingest name, lowercased | `inman-r61mh135109-ingest` |
| Container image | `ghcr.io/brain-bbqs/` + the ingest name, lowercased | `ghcr.io/brain-bbqs/suthana-in-lab-r61mh135106-ingest` |
| Dockerfile | `containers/<lab>[-<project>].Dockerfile` | `containers/suthana-in-lab.Dockerfile` |

## `code/`

Two-file shape used by the NWB labs:

- A core conversion module holding all logic that determines output content. Name it with a leading underscore when the batch driver imports it rather than running it (`_inman_to_nwb.py`, `_suthana_in_lab_to_nwb.py`). Dispatch hashes exactly one file (`script_path` in `dispatch/projects.json`) to decide when to force a reprocess, so keeping content-determining logic in one module is what makes that hash meaningful.
- `batch_convert.py`, the entrypoint dispatch actually runs. It discovers work under the incoming dandiset and loops the core converter over it.

A converter that already processes a whole incoming tree in one invocation can stay a single file, as `labs/kemere/code/convert_raw_to_bids.py` does.

When the driver imports the core module with a relative import, dispatch invokes it as a module from the repo root (`python3 -m labs.<lab>.code.batch_convert`) so the import resolves. Kemere and shepherd instead run plain script paths. Either works, just keep `convert_command` (lab-register) consistent with the choice.

## The dispatch contract for the batch driver

`dispatch/dispatch.py` runs the conversion per project on a schedule. The driver must behave so that repeated runs are safe:

- Accept `--input <incoming dandiset dir>`, `--output <standardized dir>`, and `--config <path>` (NWB labs), or equivalent explicit flags. Dispatch fills them via `{incoming_dir}`, `{standardized_dir}`, `{repo_root}` placeholders. Favor one-word flag names, mapped onto longer keyword arguments at the API level (repo `CLAUDE.md`).
- Skip work whose output already exists, unless `--overwrite` is passed. Dispatch appends the project's `overwrite_flag` automatically when the hashed `script_path` changes, which is how a code edit forces a full reprocess.
- Exit 0 on an empty incoming dandiset, reporting that nothing was found. New projects are registered before real data arrives (suthana precedent), and the first cron pass must succeed, not fail.
- Report, do not swallow: print what was discovered, converted, skipped, and ignored. tqdm progress bars over sessions are the house pattern.
- Parallelize over sessions with one worker per CPU by default and a `--jobs` cap, unless per-session memory makes that unsafe (shepherd converts serially because it decodes whole videos into memory). Say which in `code/README.md`.
- Create output parent directories itself, and write into the DANDI layout the plan specified.

## `config.yaml`

For NWB labs, the single metadata source the converter consumes. `labs/inman/code/config.yaml` is the pattern:

- A header comment pointing at the NWB GUIDE for field meanings.
- `session` and `subject` blocks covering the DANDI-required fields (species, sex `M`/`F`/`O`/`U`, age as ISO 8601 duration or date of birth), plus start time with explicit format, experimenter style notes, and `related_publications` for the intake's DOIs.
- Per-stream blocks (timeseries descriptions and units, devices, electrode groups, channel maps) matching the plan's metadata section.
- Every unconfirmed value marked `PROVISIONAL` inline, with what would confirm it. A file-top comment says provisional values keep the conversion runnable and must be replaced with real lab metadata.

BIDS labs pass project-wide values as CLI flags instead (kemere's `--species`), supplied at registration time through the `metadata` map in `dispatch/projects.json`.

## `code/README.md`

Documents, at minimum: what the converter does, the source-to-output mapping table from the plan, the expected input layout, the target output structure (the plan's expected-output example), how to run it by hand, and the naming decisions with a pointer to the single function implementing each.

## `envs/`

One file, `pyproject.toml`. Loose and intentionally unpinned. The Dockerfile resolves it fresh at build time and the image digest is the reproducibility lock, so there is no lockfile to keep in sync. Shape (see `labs/inman/envs/pyproject.toml`):

- Header comment explaining exactly that.
- `[project]` with the lowercased ingest name, `requires-python = ">=3.10"`, and the runtime dependencies.
- `[project.optional-dependencies]` with `test = ["pytest>=7"]` (plus a `dev` extra if fixture regeneration needs more).
- `[tool.setuptools] py-modules = []`, because installing it only realizes the dependency set. The converter runs as a script, it is not imported from the package.

The interpreter version (3.13) is pinned by the Dockerfile base image and the CI job, not by a file in `envs/`.

## `containers/`

`<lab>.Dockerfile`, modeled on `labs/inman/containers/inman.Dockerfile`:

- Base `neurodebian:trixie` (Debian 13, Python 3.13), matching the sibling images.
- Two `LABEL org.opencontainers.image.*` lines: `source` pointing at this repo, `description` naming the lab pipeline.
- System packages only for real system-level dependencies (kemere adds FFmpeg). Keep the apt layer minimal.
- A dedicated venv (`/opt/venv`) rather than `--break-system-packages`, Debian's interpreter is PEP 668 externally managed.
- `COPY envs/pyproject.toml` then `pip install "/tmp/build[test]"`, so the same image can run the test suite against mounted code.
- `CMD ["python", "--version"]`. CI smoke-tests the image by running its default command, so it must exit 0 fast.
- The image holds only the environment. Code and data are bind-mounted at run time, so one image serves any revision of the converter.

## `tests/`

Golden-file pattern (kemere is the fullest example):

- `example_raw/`: a small committed mock of the exact source tree, real enough to exercise the real parsing paths (tiny real media files, real text formats).
- `expected_output/`: the golden standardized tree the converter must reproduce, byte-exact for text and media, semantic comparison for JSON.
- One integration test running the converter over `example_raw/` and diffing against `expected_output/`. Unit tests only where the driver has real logic of its own (discovery, output paths, skip/overwrite bookkeeping).
- `generate_fixtures.py` to regenerate both trees on intentional behavior changes.
- Deterministic stand-ins for system tools the sandbox may lack (kemere ships a PyAV-backed `ffprobe` shim).
- For a verbatim port whose rough edges block a real end-to-end run, fall back to shepherd's pattern: an environment smoke test (imports resolve, required binaries on PATH, CLI parses) plus unit tests of the new driver with the ported entry point stubbed. State in the lab README why there is no integration test yet.

Repo `CLAUDE.md` applies: mark AI-authored tests with the `ai_generated` marker and parametrize where it reduces duplication. Fixture directories that formatters would mangle get excluded in `.pre-commit-config.yaml` and the root `pyproject.toml`.

## `prompts/`

Created by lab-intake. Keep `initial.md` current as the scaffold session proceeds, quoting each new request verbatim.

## The lab `README.md`

Mirror the section flow of `labs/kemere/README.md` and `labs/shepherd/README.md`:

1. Title (the ingest name) and a short statement of what the conversion does, linking the standard followed and the top-level README for how labs are organized.
2. Layout block for the lab directory.
3. The environment (unpinned declaration, image as the lock, where the interpreter is pinned).
4. Run it with the container (build, pull, run, test commands, with real dandiset paths).
5. Run it locally without the container.
6. Tests (what exists, how to run, `[test]` extra install line).
7. For ports: the provenance section crediting the original author, and the known rough edges list.
