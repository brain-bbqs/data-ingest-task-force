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
docs/                   Repository documentation (CI, see docs/README.md)
pyproject.toml          Repository-wide tooling (ruff)
.github/workflows/      CI: container build/test/publish + daily dev-env tests
```

## Adding a lab

Add a new `labs/<lab>/` directory, self-contained the same way as `labs/kemere/` (code, tests, `envs/`, and its own `containers/<lab>.Dockerfile` if it needs a container).
Give the Dockerfile a lab-specific name, and register the image in `.github/workflows/container_images.yml` in both places its comment points at: the registry JSON (dockerfile, build context, image name, and the test suite that gates it) and the change-detection path filters.
