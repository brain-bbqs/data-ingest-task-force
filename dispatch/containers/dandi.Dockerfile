# syntax=docker/dockerfile:1

# Portable runtime for the `dandi` CLI, published so dispatch.py's download/
# upload steps run inside a container rather than needing the dandi CLI
# installed directly on the self-hosted runner host -- the same reasoning as
# each lab's own container_image (see labs/<lab>/containers/), just for
# dispatch's own dandi download/upload steps instead of a lab's conversion
# script. Holds only the dandi CLI itself; no code or data is baked in.
FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/brain-bbqs/data-ingest-task-force"
LABEL org.opencontainers.image.description="Portable dandi CLI runtime for dispatch.py's download/upload steps."

RUN pip install --no-cache-dir dandi

CMD ["dandi", "--version"]
