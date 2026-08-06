# dispatch

Cron entrypoint for the `ember-incoming` → `ember-standardized` ingest
pipeline, invoked on a schedule by the self-hosted runner in
[`data-ingest-runner`](https://github.com/CodyCBakerPhD/data-ingest-runner)
(see that repo's `.github/workflows/cron_ingest.yml`). It is repo-level infra,
not a lab — it doesn't do any conversion itself, it just drives each
registered lab's own conversion script.

## What one run does, per registered project

1. `dandi download` the project's incoming dandiset (from the
   `dandi.emberarchive.org` instance) into `<ember-incoming>/<incoming_dandiset_id>/`.
2. Discover its sessions (`session_glob` in `projects.yaml`) and diff them
   against the project's manifest (`<ember-standardized>/<standardized_dandiset_id>/.ingest_state.json`)
   to find sessions with no conversion recorded yet.
3. If there are new sessions, **or** the conversion script's contents have
   changed since the manifest was last written (sha256, so any edit forces a
   full reprocess via `overwrite_flag`), run the lab's conversion command.
4. `dandi upload` the standardized directory.

Each lab only needs one entry in `projects.yaml` — see the file for the field
reference and the Kemere entry as a worked example.

## Layout

```
dispatch/
  dispatch.py      CLI entrypoint / orchestration (run this)
  registry.py       Loads + validates projects.yaml
  state.py          Per-project manifest (.ingest_state.json) read/write
  projects.yaml     The registry: one entry per lab
  envs/             Python env declaration (pyyaml, pytest) for dispatch.py itself
  tests/            Unit tests (no DANDI/network access needed)
```

## Running it

```bash
pip install "./dispatch/envs"

python3 dispatch/dispatch.py \
    --incoming-root      /path/to/ember-incoming \
    --standardized-root  /path/to/ember-standardized
```

Useful flags: `--only <lab>` (repeatable, restrict to specific projects),
`--skip-download`, `--skip-upload`, `--dry-run` (log every action, touch
nothing), `--repo-root` (defaults to this checkout), `--registry` (defaults
to `dispatch/projects.yaml`).

A run is safe to repeat: with nothing new and an unchanged conversion script,
every project is a no-op except the upload check (which is itself a cheap,
idempotent no-op via `dandi upload --existing refresh` when there's nothing
new to send).

## Credentials

`dispatch.py` does not manage DANDI credentials — it shells out to the
`dandi` CLI, which must already be configured on the runner for every
`dandi_instance` named in `projects.yaml` (e.g. via `dandi login -i
emberarchive`, run once on the runner) before cron invokes this script.

## Adding a project

1. Add an entry to `projects.yaml` (see the field reference at the top of
   that file).
2. Make sure `session_glob` matches exactly the raw session directories your
   lab's converter expects as input, and that `convert_command` uses
   `{repo_root}` / `{incoming_dir}` / `{standardized_dir}` to reach them.
3. If reprocessing on a script change should pass a flag (like Kemere's
   `--overwrite`), set `overwrite_flag`; otherwise the script's own default
   behavior on already-existing output applies.

## Tests

```bash
pip install "./dispatch/envs[test]"
python3 -m pytest dispatch/tests -q
```

These are unit tests only (registry validation, manifest read/write, command
templating with `subprocess.run` mocked out) — no DANDI, network, or self-hosted
runner needed to run them, and they run in `test.yml` CI alongside the lab
tests.
