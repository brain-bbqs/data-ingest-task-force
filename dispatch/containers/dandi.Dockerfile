# syntax=docker/dockerfile:1

# Portable runtime for the `dandi` CLI, published so dispatch.py's download/
# upload steps run inside a container rather than needing the dandi CLI
# installed directly on the self-hosted runner host -- the same reasoning as
# each lab's own container_image (see labs/<lab>/containers/), just for
# dispatch's own dandi download/upload steps instead of a lab's conversion
# script. Holds only the environment; no code or data is baked in.
FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/brain-bbqs/data-ingest-task-force"
LABEL org.opencontainers.image.description="Portable dandi CLI runtime for dispatch.py's download/upload steps."

# Alongside the dandi CLI itself, the dispatch `test` extra (pytest +
# jsonschema) is installed so this same image can also run dispatch's test
# suite against mounted code. Publishing the image is gated on that suite
# (see .github/workflows/container_images.yml), mirroring the lab images.
#
# The dandi floor is the only version constraint here. Every download
# dispatch.py runs passes `-e refresh`, which skipped nothing at all on
# filesystems that store mtimes at coarser than sub-second granularity
# (dandi/dandi-cli#1907), so each pass re-fetched whole dandisets instead of
# refreshing them. Fixed upstream in 0.78.0 by dandi/dandi-cli#1910. The
# floor makes a build fail loudly rather than resolve back to a dandi
# without the fix.
COPY envs/pyproject.toml /tmp/build/pyproject.toml
RUN pip install --no-cache-dir "dandi>=0.78.0" "/tmp/build[test]" \
    && rm -rf /tmp/build

CMD ["dandi", "--version"]
