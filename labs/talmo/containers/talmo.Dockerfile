# syntax=docker/dockerfile:1

# The container is this project's pinned, reproducible runtime environment and
# the official way to run the conversion pipeline. The loose dependencies
# declared in envs/pyproject.toml are resolved fresh at build time, and the
# resulting image (by digest) is the lock. There is no lockfile in the
# repository to hold in sync.
#
# The image holds only the environment, not the code. The code and the data
# are bind-mounted at run time, so a single image serves any revision of the
# converter.
#
# NeuroDebian trixie (Debian 13) is the base layer, matching the sibling
# images. It provides Python 3.13 and a recent FFmpeg. The converter shells out
# to `ffprobe` to read video metadata, its one system dependency.
FROM neurodebian:trixie

LABEL org.opencontainers.image.source="https://github.com/brain-bbqs/data-ingest-task-force"
LABEL org.opencontainers.image.description="Pinned runtime environment for the Talmo-lab LUC3D-to-BIDS conversion pipeline (labs/talmo/)."

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        git \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Debian's system interpreter is externally managed (PEP 668), so install into
# a dedicated virtual environment.
RUN python3 -m venv "${VIRTUAL_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

# The `test` extra is installed too, so this same image can run the test suite
# against mounted code.
COPY envs/pyproject.toml /tmp/build/pyproject.toml
RUN pip install "/tmp/build[test]" \
    && rm -rf /tmp/build

CMD ["python", "--version"]
