# dispatch

Cron entrypoint for the `ember-incoming` → `ember-standardized` ingest pipeline, invoked on a schedule by the self-hosted runner in [`data-ingest-runner`](https://github.com/CodyCBakerPhD/data-ingest-runner) (see that repo's `.github/workflows/cron_ingest.yml`).
It is repo-level infra, not a lab — it doesn't do any conversion itself, it just drives each registered lab's own conversion script.

## What one run does, per registered project

1. `dandi download` the project's incoming dandiset (from its `dandi_instance`, default `ember-dandi`) into `<ember-incoming>/<incoming_dandiset_id>/`. Runs inside `--dandi-image` (`docker pull` + `docker run`), not directly on the runner host.
2. Discover its sessions (per `sessions.json`'s spec for the lab) and diff them against the project's manifest (`<ember-standardized>/<standardized_dandiset_id>/.ingest_state.json`) to find sessions with no conversion recorded yet.
3. If there are new sessions, **or** the conversion script's contents have changed since the manifest was last written (sha256, so any edit forces a full reprocess via `overwrite_flag`), run the lab's conversion command.
   If the project names a `container_image`, this step runs inside it (`docker pull` + `docker run`) instead of directly on the runner host — the image holds only the lab's runtime environment (e.g. FFmpeg for Kemere), not the code or data, which are bind-mounted in at run time from the same host paths. Otherwise it runs directly on the runner host, which must then already have whatever the conversion script needs installed.
4. `dandi upload` the standardized directory, also inside `--dandi-image` — first fetching just that dandiset's `dandiset.yaml` (not a full download), since `dandi upload` needs one already on disk to know which dandiset it's uploading to, and one only lands there on its own when `standardized_dandiset_id` happens to equal `incoming_dandiset_id`. This step is skipped entirely when step 3 had nothing to do — upload's no-op check still re-checksums the whole local dandiset every pass (`DANDI_CACHE=ignore` disables the digest cache), a cost that grows with the dandiset. The tradeoff: if a run converts sessions but dies before its upload finishes, the next pass will not retry that upload on its own (the manifest already records the sessions). Recover by re-uploading manually, or by touching the conversion script so the hash change forces a reprocess + upload.

Every external tool dispatch drives runs in a container, not directly on the runner host — steps 1 and 4 in `--dandi-image` (default: this repo's own `dispatch/containers/dandi.Dockerfile`, published as `ghcr.io/brain-bbqs/dandi-cli`), step 3 in the project's own `container_image`. The runner host itself only needs `python3` (to run `dispatch.py` — see the top-level docstring for why that part stays native) and `docker`.

Every dandi invocation (steps 1 and 4) also sets `DANDI_CACHE=ignore`, disabling dandi-cli's on-disk checksum cache: it buys nothing here, since every `--dandi-image` container is `--rm` and starts with an empty cache dir anyway, and a fresh cache dir has a known joblib race that can fail an upload outright (`failed to compute digest: ... func_code.py`).

Each lab needs one entry in `projects.json` (dandiset ids, conversion command) and one in `sessions.json` (how to discover its sessions) — see each file for the field reference, and the Kemere entries as a worked example.

## Layout

```
dispatch/
  dispatch.py       CLI entrypoint / orchestration (run this)
  registry.py       Loads + validates projects.json
  sessions.py        Loads + validates sessions.json, discovers sessions on disk
  state.py           Per-project manifest (.ingest_state.json) read/write
  projects.json      The project registry: dandiset ids + conversion command, one entry per lab
  sessions.json       The session-discovery registry: one entry per lab
  schemas/           JSON Schemas for both registry files (editor validation, see below)
  containers/        dandi.Dockerfile -- the portable dandi CLI runtime the
                       download/upload steps run inside (see container_images.yml)
  envs/              Python env declaration (pytest) for dispatch.py itself
  tests/             Unit tests (no DANDI/network access needed)
```

`sessions.json` is deliberately a separate file from `projects.json`.
Session discovery doesn't reduce to a single glob in general — a lab may need several raw subtrees (multiple `include` patterns) or exclusions (stray non-session directories) — and that shape can evolve independently of a project's dandiset ids or conversion command.

### `projects.json` fields

| Field | Meaning |
| --- | --- |
| `lab` | Must match both the `labs/<lab>/` directory and its `sessions.json` key. |
| `incoming_dandiset_id` | Six-digit dandiset id on the ember archive holding the raw upload. |
| `standardized_dandiset_id` | Six-digit dandiset id the converted/standardized output is uploaded to. May equal `incoming_dandiset_id` if raw and standardized data share one dandiset (as with Kemere). |
| `script_path` | Path (repo-root-relative) to the conversion script, hashed to detect when it changes. |
| `convert_command` | Argv list to run the conversion. Tokens may use `{repo_root}`, `{incoming_dir}`, `{standardized_dir}`, plus any key from `metadata` (e.g. `{species}`) — rarely needed, since `metadata` entries are auto-appended as flags (see below); only reach for a placeholder when a value needs to land somewhere other than a trailing flag. |
| `dandi_instance` | DANDI archive instance name (per `dandi instance-list`), default: `ember-dandi`. |
| `overwrite_flag` | Optional single flag appended to `convert_command` when `script_path`'s hash has changed, so the script reprocesses sessions it would otherwise skip. |
| `container_image` | Optional image (e.g. `ghcr.io/brain-bbqs/kemere-r34da059514-ingest:latest`) to run `convert_command` inside via `docker run`, rather than directly on the runner host. Holds only the lab's runtime environment — code and data are bind-mounted in at run time, not baked into the image. Omit to run directly on the host. |
| `metadata` | Optional object of project-wide string values (e.g. `{"species": "Ovis aries"}`). Each entry is automatically appended to `convert_command` as its own `--<key> <value>` flag (underscores in the key become dashes) — a lab's own command template doesn't need to name it. Keys may not reuse the reserved `repo_root`/`incoming_dir`/`standardized_dir` placeholder names. |

### `sessions.json` fields

Keyed by lab name, under a top-level `"labs"` object. Each entry has:

| Field | Meaning |
| --- | --- |
| `include` | Non-empty list of globs (relative to the incoming project dir) whose directory matches are sessions. Matches from all patterns are unioned; only directories count (stray files alongside them are ignored). |
| `exclude` | Optional list of globs to drop from that union, matched against either the session's basename or its path relative to the incoming project dir. |

A session's id is its directory's basename.

### Schemas, and editing the registry outside this repo

Both files carry a `"$schema"` pointer (`dispatch/schemas/projects.schema.json` / `sessions.schema.json`) so editors with JSON Schema support (VS Code's built-in one, for example) give inline validation and autocomplete while you edit — required fields, the six-digit dandiset id pattern, unknown-field typos, etc.
`dispatch/tests/test_schema.py` validates the committed files against these schemas in CI, and exercises each schema against a few known-bad shapes so a schema edit that silently stops catching something gets caught too.

`dispatch.py --registry`/`--sessions` accept any path, not just these committed files — a self-hosted runner can point them at a `projects.json`/`sessions.json` living outside the repo (e.g. on the runner host) so the registry can be edited without a commit/PR.
See `data-ingest-runner`'s README (`REGISTRY_PATH`/`SESSIONS_PATH`) for how the cron workflow wires that up.
A relative `"$schema"` pointer only resolves for editors when the file is opened from its committed location in this repo, so an externally-hosted copy should either point `"$schema"` at this repo's raw GitHub URL for the schema file, or drop it — dispatch.py itself doesn't require or read `"$schema"`.

## Running it

```bash
pip install "./dispatch/envs"

python3 dispatch/dispatch.py --dry-run   # or drop --dry-run to actually run
```

`--incoming-root`/`--standardized-root` default to `ember-incoming`/`ember-standardized` siblings of `--repo-root`, created as needed — no path required for the common case. Pass them explicitly to put the data somewhere else. Whatever is supplied or defaulted is always resolved to an absolute path before use (a relative one would reach `docker run -v` as a relative host path, which Docker rejects).

Useful flags: `--only <lab>` (repeatable, restrict to specific projects), `--skip-download`, `--skip-upload`, `--dry-run` (log every action, touch nothing), `--repo-root` (defaults to this checkout), `--registry` (defaults to `dispatch/projects.json`), `--sessions` (defaults to `dispatch/sessions.json`), `--dandi-image` (defaults to `ghcr.io/brain-bbqs/dandi-cli:latest`, this repo's own `dispatch/containers/dandi.Dockerfile`).

A run is safe to repeat: with nothing new and an unchanged conversion script, every project is a no-op — download refresh, then straight to the next project, no conversion and no upload.

## Credentials

`dispatch.py` does not manage DANDI or container-registry credentials itself:

- `dandi` runs only inside `--dandi-image`, never on the bare runner host, so its credentials come entirely from an env var already present in dispatch's own environment (e.g. set by the calling workflow — see `data-ingest-runner`'s README). The var name is per-`dandi_instance`, following dandi-cli's own convention (not this script's): the instance name, upper-cased, `-` → `_`, suffixed `_API_KEY` (`ember-dandi` → `EMBER_DANDI_API_KEY`; see `dandi_api_key_env_var()`) — there is no single generic `DANDI_API_KEY` that authenticates every instance. Dispatch forwards that variable into every container it starts by name only (`docker run -e EMBER_DANDI_API_KEY`, no `=value`), never as a literal value on the argv. This same key is also forwarded into a project's `container_image` when one's set, so a lab's conversion step can use it too, without the secret ever appearing in a logged command line;
- `docker` itself, which must already be logged in for any private image dispatch names — `--dandi-image` or a project's `container_image` (e.g. `docker login ghcr.io`, run once on the runner) — GHCR packages default to private.

## Adding a project

1. Add an entry to `projects.json` (see the field reference above). If the lab publishes a container image (see its own `containers/<lab>.Dockerfile` and `.github/workflows/container_images.yml`), set `container_image` to it so the conversion step doesn't need its runtime dependencies installed directly on the runner host.
2. Add a matching entry (same `lab` key) to `sessions.json` describing how to discover its sessions.
3. Make sure `convert_command` uses `{repo_root}` / `{incoming_dir}` / `{standardized_dir}` to reach the right paths.
4. If reprocessing on a script change should pass a flag (like Kemere's `--overwrite`), set `overwrite_flag`; otherwise the script's own default behavior on already-existing output applies.

Note: Kemere's `incoming_dandiset_id` in `projects.json` is still a placeholder (`000477`) — fill it in with the real assigned id before relying on a cron run against it. (`standardized_dandiset_id` is the real assigned id, `000525`.)

Note: Inman's registration (incoming `000519`, standardized `000526`) runs `labs/inman/code/batch_convert.py` (as `python3 -m labs.inman.code.batch_convert`, so its relative import of the core module resolves), which converts every `.mat` walk file found under the incoming dandiset in one invocation (skipping walks whose output NWB already exists, unless dispatch appends `--overwrite`). Its `script_path` deliberately stays pointed at `_inman_to_nwb.py`, since that is where the conversion logic that determines output content lives. The incoming dandiset currently holds a single sample session folder (`sourcedata/raw/sample-1`) with one `.mat` file, which doubles as the end-to-end smoke test for runner runs. The session metadata in `labs/inman/code/config.yaml` is still provisional (marked PROVISIONAL in the file). Replace it with the real lab metadata before treating the standardized output as final.

Note: Shepherd's registration (incoming `000528`, standardized `000529`) is **not yet ready for a real cron run**, and its `convert_command` is a placeholder.
`labs/shepherd/code/shepherd_to_nwb.py` is a verbatim port of the original conversion work and converts one session per invocation, taking `--subject` and `--session` on the command line, so it cannot process a whole incoming dandiset the way Kemere's and Inman's commands do.
The committed command names a single `sourcedata/raw/sample-1` session with placeholder subject and session values, mirroring how Inman was first registered before `batch_convert.py` existed.
Before enabling this project on the runner it needs a batch driver (see `labs/inman/code/batch_convert.py` for the shape of one), real metadata in `labs/shepherd/code/config.yaml`, and the converter's known rough edges fixed — all listed in `labs/shepherd/README.md`.
Until then, restrict runner runs with `--only kemere --only inman`, or leave `000528` empty so session discovery finds nothing and the conversion step is skipped.

## Tests

```bash
pip install "./dispatch/envs[test]"
python3 -m pytest dispatch/tests -q
```

These are unit tests only (registry/session-spec validation, manifest read/write, command templating/dry-run with `subprocess.run` mocked out, and the committed registry files against their JSON Schemas) — no DANDI, network, or self-hosted runner needed to run them, and they run in `test.yml` CI alongside the lab tests.
