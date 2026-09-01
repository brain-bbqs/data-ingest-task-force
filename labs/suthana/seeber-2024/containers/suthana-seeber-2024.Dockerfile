# syntax=docker/dockerfile:1

# The container is this project's pinned, reproducible runtime environment and
# the official way to run the conversion pipeline. The loose dependencies
# declared in envs/pyproject.toml are resolved fresh at build time, and the
# resulting image (by digest) is the lock. There is no lockfile in the
# repository to hold in sync.
#
# The image holds only the environment, not the code. The code (and the data)
# are supplied at run time -- checked out or bind-mounted -- so a single image
# serves any revision of the converter.
#
# NeuroDebian trixie (Debian 13) is the base layer, matching the sibling
# Kemere, Inman, Shepherd, Sanes and Suthana in-lab images. It provides Python
# 3.13. This pipeline has no system-level dependencies: the source .mat files
# are ordinary (non-v7.3) MATLAB files, read with scipy's MATLAB reader.
FROM neurodebian:trixie

LABEL org.opencontainers.image.source="https://github.com/brain-bbqs/data-ingest-task-force"
LABEL org.opencontainers.image.description="Pinned runtime environment for the Suthana-lab seeber-2024 group-subject-to-NWB conversion pipeline (labs/suthana/seeber-2024/)."

# Python, and the basics for cloning and TLS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Debian's system interpreter is externally managed (PEP 668), so install into a
# dedicated virtual environment rather than forcing pip with
# --break-system-packages. This also keeps our dependencies cleanly separated
# from the apt-managed Python packages.
RUN python3 -m venv "${VIRTUAL_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

# The `test` extra adds pytest so this same image can also run the integration
# test against mounted code.
COPY envs/pyproject.toml /tmp/build/pyproject.toml
RUN pip install "/tmp/build[test]" \
    && rm -rf /tmp/build

CMD ["python", "--version"]
