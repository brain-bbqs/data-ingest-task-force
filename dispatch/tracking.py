"""The tracking dataset: a DataLad dataset (brain-bbqs/data-ingest-runner-
tracking, cloned once on the runner) that holds every container image
dispatch runs in and a provenance record of every conversion and upload.

Images live under ``envs/<name>.sif``, registered with ``datalad
containers-add`` from a digest-pinned ``docker://`` URL. Each image is
re-resolved every run and rebuilt only when its tag has moved, so an image
change is itself a commit. The ``.sif`` files are annexed and stay on the
runner. GitHub holds only the git history, and each image's pinned URL
(``datalad.containers.<name>.updateurl``) is enough to rebuild it anywhere.

Steps run through ``datalad containers-run`` with CALL_FORMAT, which wraps
the container in con-duct. Each run's outputs are its record directory,
``records/<project key>/<UTC stamp>-<step>/``, holding:

- ``context.json``: what dispatch knew going in (project, dandisets,
  pinned image, task-force commit, sessions), written before the run
- con-duct's ``info.json``, ``usage.jsonl``, ``stdout``, and ``stderr``
- ``manifest.json`` for conversions: every output file written, with its
  sha256 (see record_run.py)

so each record is one commit, with DataLad's run record in its message.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from commands import run
from images import container_name, resolve_digest

log = logging.getLogger("dispatch")

# --fail-time 0 keeps con-duct's logs for a command that fails fast, which
# is exactly when they're wanted. Apptainer itself takes its binds, working
# directory, and forwarded variables from the environment dispatch sets up
# (APPTAINER_BIND, APPTAINER_PWD, APPTAINERENV_*), so one call format serves
# every step.
CALL_FORMAT = "duct --fail-time 0 apptainer exec --cleanenv {img} {cmd}"

ENVS_DIRNAME = "envs"
RECORDS_DIRNAME = "records"


class TrackingError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrackedImage:
    name: str
    path: Path
    url: str


def read_container_config(config_path: Path, /) -> dict[str, dict[str, str]]:
    """The ``datalad.containers.*`` sections of a dataset's .datalad/config,
    keyed by container name. A minimal git-config reader, since dispatch
    stays standard-library only and doesn't import datalad itself."""
    containers: dict[str, dict[str, str]] = {}
    if not config_path.is_file():
        return containers
    current = None
    prefix = '[datalad "containers.'
    for raw_line in config_path.read_text().splitlines():
        line = raw_line.strip()
        if line.startswith("["):
            current = line[len(prefix) : -2] if line.startswith(prefix) and line.endswith('"]') else None
            continue
        if current is None or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        containers.setdefault(current, {})[key] = value
    return containers


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class TrackingDataset:
    root: Path
    _images: dict[str, TrackedImage] = field(default_factory=dict)

    def check(self) -> None:
        if not (self.root / ".datalad" / "config").is_file():
            raise TrackingError(
                f"{self.root} is not a DataLad dataset. Clone it first: "
                f"datalad clone https://github.com/brain-bbqs/data-ingest-runner-tracking {self.root}"
            )

    def image(self, *, image: str, dry_run: bool) -> TrackedImage:
        """The local .sif for *image*, (re)building it first when the tag
        now points at a digest the dataset hasn't recorded. Resolved once
        per image per dispatch run."""
        if image in self._images:
            return self._images[image]
        name = container_name(image)
        path = self.root / ENVS_DIRNAME / f"{name}.sif"
        if dry_run:
            log.info("[dry-run] would resolve %s and refresh %s if its digest moved", image, path)
            return TrackedImage(name=name, path=path, url=image)

        url = resolve_digest(image)
        config = read_container_config(self.root / ".datalad" / "config").get(name, {})
        if config.get("updateurl") != url or not path.exists():
            log.info("refreshing container %s from %s", name, url)
            # containers-add doesn't record a docker:// source itself. Setting
            # it first means its own save commits it alongside the image.
            run(
                ["git", "config", "--file", ".datalad/config", f"datalad.containers.{name}.updateurl", url],
                cwd=self.root,
                dry_run=False,
            )
            add_cmd = [
                "datalad",
                "containers-add",
                name,
                "--url",
                url,
                "--image",
                f"{ENVS_DIRNAME}/{name}.sif",
                "--call-fmt",
                CALL_FORMAT,
            ]
            if "image" in config:
                add_cmd.append("--update")
            run(add_cmd, cwd=self.root, dry_run=False)
        tracked = TrackedImage(name=name, path=path, url=url)
        self._images[image] = tracked
        return tracked

    def new_record_dir(self, *, project_key: str, step: str) -> Path:
        record_dir = self.root / RECORDS_DIRNAME / project_key / f"{utc_stamp()}-{step}"
        return record_dir

    def record(
        self,
        *,
        cmd: list[str],
        container: str | None,
        record_dir: Path,
        context: dict,
        message: str,
        env: dict[str, str],
        dry_run: bool,
    ) -> None:
        """Run *cmd* as one recorded step: inside *container* via
        ``datalad containers-run``, or with ``datalad run`` under con-duct
        directly on the host when *container* is None."""
        relative = record_dir.relative_to(self.root)
        # datalad run treats {...} in a command as its own placeholders.
        escaped = [token.replace("{", "{{").replace("}", "}}") for token in cmd]
        if container is not None:
            argv = ["datalad", "containers-run", "--container-name", container]
        else:
            argv = ["datalad", "run"]
            escaped = ["duct", "--fail-time", "0"] + escaped
        argv += ["--explicit", "--output", str(relative), "--message", message, "--"] + escaped
        env = {**env, "DUCT_OUTPUT_PREFIX": f"{record_dir}/"}

        if dry_run:
            run(argv, cwd=self.root, env=env, dry_run=True)
            return
        record_dir.mkdir(parents=True, exist_ok=True)
        context_path = record_dir / "context.json"
        context_path.write_text(json.dumps(context, indent=2, sort_keys=True) + "\n")
        # Staged rather than left untracked, which datalad run refuses as an
        # output, so the run's own commit picks it up.
        run(["git", "add", str(context_path.relative_to(self.root))], cwd=self.root, dry_run=False)
        try:
            run(argv, cwd=self.root, env=env, dry_run=False)
        except subprocess.CalledProcessError:
            # datalad run leaves a failed run's outputs unsaved. Keep them:
            # con-duct's logs of a failure are the record most worth having.
            try:
                run(
                    ["datalad", "save", "--message", f"{message} (failed)", str(relative)], cwd=self.root, dry_run=False
                )
            except subprocess.CalledProcessError:
                log.exception("could not save the record of a failed run at %s", record_dir)
            raise
