# CI

- **Container images** (`.github/workflows/container_images.yml`) are the main
  PR gate. A change-detection job first works out which registered images the
  changeset touches (`labs/kemere/**` for the kemere image, `dispatch/**` for
  the dandi image, plus the workflow file itself for all of them), so PR cost
  stays proportional to the change as labs are added. Each affected image is
  built fresh (no layer cache, so the unpinned environments are re-resolved)
  and its own test suite runs inside that exact build. Pull requests stop
  there. On a merge to main the same run then publishes the tested image
  itself to `ghcr.io/brain-bbqs/<image>` (`latest` + commit SHA tags), so
  nothing reaches GHCR without passing its suite. A manual `workflow_dispatch`
  builds, tests, and publishes every image regardless of changes, which is how
  to refresh the images without a code change. The `ContainerGate` job is the
  one stable check to require in branch protection. It passes when every
  affected image passed, including when no image was affected.
- **Python dev environment (daily tests)**
  (`.github/workflows/daily_tests.yml`) re-run the pip-installed
  (uncontainerized) suite from `.github/workflows/test.yml` at 12:00 UTC and
  email on failure. The dev environments are unpinned, so a dependency
  release alone can break them with no commit to trigger a CI run. Requires
  the `MAIL_USERNAME` and `MAIL_PASSWORD` repository secrets.
