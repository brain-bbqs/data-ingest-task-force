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

# Which dandi to install. The default is the current release from PyPI, which
# is what the published :latest image is built from. Override it to build an
# experimental image against an unreleased fix, e.g.
#
#   --build-arg DANDI_SPEC="dandi @ git+https://github.com/dandi/dandi-cli.git@refs/pull/1910/head"
#
# See .github/workflows/experimental_dandi_image.yml, which does exactly that.
ARG DANDI_SPEC=dandi

# Alongside the dandi CLI itself, the dispatch `test` extra (pytest +
# jsonschema) is installed so this same image can also run dispatch's test
# suite against mounted code. Publishing the image is gated on that suite
# (see .github/workflows/container_images.yml), mirroring the lab images.
COPY envs/pyproject.toml /tmp/build/pyproject.toml
# git is installed only when DANDI_SPEC actually names a VCS ref, so the
# default (PyPI) build -- the one published as :latest -- stays exactly as it
# was, with no git in the image and no apt work at all.
RUN set -eu; \
    case "$DANDI_SPEC" in \
      *git+*) \
        apt-get update; \
        apt-get install -y --no-install-recommends git; \
        rm -rf /var/lib/apt/lists/*; \
        ;; \
    esac; \
    pip install --no-cache-dir "$DANDI_SPEC" "/tmp/build[test]"; \
    rm -rf /tmp/build

CMD ["dandi", "--version"]
