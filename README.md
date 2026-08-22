# Data Ingest Task Force

Data ingest pipelines for the BRAIN-BBQS labs, staging raw lab data into standardized formats (BIDS / NWB) ahead of DANDI upload.

Each lab's codebase is self-contained under `labs/<lab>/` — its own conversion code, tests, Python environment declaration, and Dockerfile — so labs can evolve independently without stepping on each other.

A scheduled self-hosted runner (in [`data-ingest-runner`](https://github.com/CodyCBakerPhD/data-ingest-runner)) periodically calls `dispatch/dispatch.py`, which refreshes a local copy of each lab's incoming dandiset, runs its conversion script on any new sessions, and uploads the standardized output.
See `dispatch/README.md` for more details.

## Layout

```
labs/
  kemere/               Kemere lab: raw behavioral recordings -> BEP047 BIDS
                         (see labs/kemere/README.md)
dispatch/               Cron entrypoint driving all labs' conversions
                         (see dispatch/README.md), including its own
                         containers/dandi.Dockerfile -- the portable dandi
                         CLI runtime dispatch.py's download/upload steps
                         run inside, same pattern as a lab's own container
pyproject.toml          Repository-wide tooling (ruff)
.github/workflows/      CI: container build/test/publish + daily dev-env tests
```

## Adding a lab

Add a new `labs/<lab>/` directory, self-contained the same way as `labs/kemere/` (code, tests, `envs/`, and its own `containers/<lab>.Dockerfile` if it needs a container).
Give the Dockerfile a lab-specific name, and register the image in the matrix of `.github/workflows/container_images.yml` (dockerfile, build context, image name, and the test suite that gates it).

## CI

- **Container images** (`.github/workflows/container_images.yml`) are the main
  PR gate. Every run builds each registered image fresh (no layer cache, so
  the unpinned environments are re-resolved) and runs the image's own test
  suite inside that exact build. Pull requests stop there. On a merge to main
  the same run then publishes the tested image itself to
  `ghcr.io/brain-bbqs/<image>` (`latest` + commit SHA tags), so nothing
  reaches GHCR without passing its suite. A manual `workflow_dispatch` does
  the same, which is how to refresh the images without a code change.
- **Python dev environment (daily tests)**
  (`.github/workflows/daily_tests.yml`) re-run the pip-installed
  (uncontainerized) suite from `.github/workflows/test.yml` at 12:00 UTC and
  email on failure. The dev environments are unpinned, so a dependency
  release alone can break them with no commit to trigger a CI run. Requires
  the `MAIL_USERNAME` and `MAIL_PASSWORD` repository secrets.
