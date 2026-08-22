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
COPY envs/pyproject.toml /tmp/build/pyproject.toml
RUN pip install --no-cache-dir dandi "/tmp/build[test]" \
    && rm -rf /tmp/build

CMD ["dandi", "--version"]
