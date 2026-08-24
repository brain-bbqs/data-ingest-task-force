---
name: lab-register
description: Wire a scaffolded BRAIN-BBQS lab or project into this repository's shared machinery, covering the dispatch registries (projects.json, sessions.json), CI image registration in container_images.yml, the dev-environment job in test.yml, and the README entries. Use it after lab-scaffold, and also whenever someone asks to register a lab, hook a conversion into dispatch or the cron runner, record dandiset ids, or publish a lab's container image. Registration is complete only when the dispatch tests pass and a dry run resolves the new entry.
---

# Lab register

Connect a scaffolded `labs/<lab>/` codebase to everything that runs it. There are six touchpoints. Missing any of them leaves the lab invisible to cron, CI, or readers, so work through all six.

The project key is the lab name alone, or `<lab>/<project>` when the lab has more than one collection. Use it consistently everywhere below.

## 1. `dispatch/projects.json`

Add one entry. The field reference lives in `dispatch/README.md`, and the existing entries are worked examples. Points that need thought:

- `script_path` points at the file holding the content-determining conversion logic (inman points at `_inman_to_nwb.py`, not the batch driver). Its hash is what triggers reprocessing.
- `convert_command` is an argv list using `{repo_root}`, `{incoming_dir}`, `{standardized_dir}`. Use module invocation (`python3 -m labs.<lab>.code.batch_convert`) when the driver relies on a relative import.
- `overwrite_flag` is the flag the driver understands (house convention `--overwrite`).
- `container_image` is the lab's GHCR image with the `:latest` tag. The image only exists on GHCR after the branch merges to main and CI publishes it, so a real cron run cannot use the entry before that first merge.
- Project-wide scalar metadata (kemere's species) goes in the `metadata` map. Each entry is auto-appended to the command as `--<key> <value>`, so the command template does not name it.
- Set `project` only for a multi-collection lab. It must match the `labs/<lab>/<project>/` directory.

## 2. `dispatch/sessions.json`

Add an entry under `"labs"` with the same project key. `include` globs are relative to the incoming project directory, only directories count as sessions, and a session's id is its directory basename. Derive the glob from the intake's source tree (kemere: `sourcedata/raw/*-Session*`). Use `exclude` for stray non-session directories. If the incoming dandiset currently holds data the converter cannot read, scope the glob so discovery finds only real input, as shepherd does with `sourcedata/raw/sessions/*`.

## 3. `.github/workflows/container_images.yml`

Register the image in both places its top comment points at, using the lowercased ingest name:

- the path filters in the `Changes` job (the lab or project directory as `labs/<lab>/**`, plus the workflow file itself),
- the registry JSON (image name, dockerfile path, the lab or project directory as the build context, and its `tests` path as the suite that gates publishing).

## 4. `.github/workflows/test.yml`

Add a job following the existing per-lab jobs: checkout, Python 3.13, `pip install "./labs/<lab>/envs[test]"`, run the lab's pytest suite. Name it `<Lab>Integration`, or `<Lab>Smoke` when the suite is shepherd-style smoke tests. The daily scheduled run calls this same workflow, so the new environment gets exercised even without commits.

## 5. Top-level `README.md`

Add the lab to the Layout block, one line in the established format: lab key, a few words on what it converts and to which standard, and the pointer to the lab README.

## 6. `dispatch/README.md`

Append a note paragraph in the "Adding a project" section stating the registration facts and its readiness, matching the existing notes: the dandiset ids, what the registered command does, and anything provisional. Be explicit when the project is not yet ready for a real cron run, including how to keep the runner off it (`--only` the ready projects, or leave the incoming dandiset empty so discovery finds nothing).

## Placeholders and readiness

- A dandiset id not yet assigned gets a plausible placeholder plus an explicit note in `dispatch/README.md` (kemere's incoming id is the precedent). Never leave a placeholder undocumented.
- An empty incoming dandiset is fine. The batch driver exits 0 having found nothing, so the first cron pass succeeds.
- The runner authenticates per instance via `<INSTANCE>_API_KEY` env vars and needs `docker login` for private GHCR images. Both are runner-side setup, nothing to commit here, but say so in the note if the lab needs anything unusual.

## Validate

Run all three before handing off:

```bash
pip install "./dispatch/envs[test]"
python3 -m pytest dispatch/tests -q
python3 dispatch/dispatch.py --dry-run --only <project key>
```

The dispatch tests validate both registry files against their JSON Schemas. The dry run proves the new entry loads, templates its command, and touches nothing. Then run `pre-commit` on everything changed, and hand the branch back with the readiness state stated plainly.

Before handing back, run the lab-lessons skill. If this conversion taught anything the skills should know, this is when it gets encoded.
