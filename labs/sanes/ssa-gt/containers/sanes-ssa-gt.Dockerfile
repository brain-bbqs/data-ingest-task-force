FROM neurodebian:trixie
LABEL org.opencontainers.image.source="https://github.com/brain-bbqs/data-ingest-task-force"
LABEL org.opencontainers.image.description="Sanes SSA GT conversion runtime"
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates ffmpeg python3 python3-pip python3-venv && rm -rf /var/lib/apt/lists/*
ENV VIRTUAL_ENV=/opt/venv PIP_NO_CACHE_DIR=1 PATH="/opt/venv/bin:${PATH}"
RUN python3 -m venv /opt/venv
COPY envs/pyproject.toml /tmp/build/pyproject.toml
RUN pip install "/tmp/build[test]" && rm -rf /tmp/build
CMD ["python", "--version"]
