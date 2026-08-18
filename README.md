# Data Ingest Task Force

Data ingest pipelines for the BRAIN-BBQS labs, staging raw lab data into standardized formats (BIDS / NWB) ahead of DANDI upload.

Each lab's codebase is self-contained under `labs/<lab>/` — its own conversion code, tests, Python environment declaration, and Dockerfile — so labs can evolve independently without stepping on each other.

## Layout

```
labs/
  kemere/               Kemere lab: raw behavioral recordings -> BEP047 BIDS
                         (see labs/kemere/README.md)
pyproject.toml          Repository-wide tooling (ruff)
.github/workflows/      CI: tests + manually-triggered container builds
```

## Adding a lab

Add a new `labs/<lab>/` directory, self-contained the same way as `labs/kemere/` (code, tests, `envs/`, and its own `containers/<lab>.Dockerfile` if it needs a container).
Give the Dockerfile a lab-specific name; the build workflow builds one named Dockerfile per run, not "the" Dockerfile.

## CI

- **Tests** (`.github/workflows/test.yml`) run on every push/PR.
- **Daily tests** (`.github/workflows/daily_tests.yml`) re-run that same suite
  at 12:00 UTC and email on failure. The lab environments are unpinned, so a
  dependency release alone can break the suite with no commit to trigger a PR
  run. Requires the `MAIL_USERNAME` and `MAIL_PASSWORD` repository secrets.
- **Container builds** (`.github/workflows/build_and_upload_docker_image.yml`)
  are manual-only (`workflow_dispatch`). Trigger a build from the Actions tab
  (or `gh workflow run`), picking the branch/tag to build from and pointing
  `dockerfile`/`context`/`image` inputs at the lab's Dockerfile. Every run
  always builds and publishes to `ghcr.io/brain-bbqs/<image>`.
