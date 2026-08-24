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
  inman/                Inman lab: restructured .mat walk sessions -> NWB
                         (see labs/inman/README.md)
  shepherd/             Shepherd lab: multicamera rat feeding behavior -> NWB
                         (see labs/shepherd/README.md)
  suthana/              Suthana lab, one directory per project
    in-lab/               in-lab navigation: iEEG + scalp EEG + motion capture -> NWB
                           (see labs/suthana/in-lab/README.md)
dispatch/               Cron entrypoint driving all labs' conversions
                         (see dispatch/README.md), including its own
                         containers/dandi.Dockerfile -- the portable dandi
                         CLI runtime dispatch.py's download/upload steps
                         run inside, same pattern as a lab's own container
docs/                   Repository documentation (CI, see docs/README.md)
pyproject.toml          Repository-wide tooling (ruff)
.github/workflows/      CI: container build/test/publish + daily dev-env tests
.agents/skills/         Agent skills for setting up a new conversion
                         (portable SKILL.md format, see AGENTS.md;
                         .claude/skills is a symlink to it)
AGENTS.md               Entry point for AI coding agents, whatever the tool
```

## Adding a lab

Add a new `labs/<lab>/` directory, self-contained the same way as `labs/kemere/` (code, tests, `envs/`, and its own `containers/<lab>.Dockerfile` if it needs a container).
Give the Dockerfile a lab-specific name, and register the image in `.github/workflows/container_images.yml` in both places its comment points at: the registry JSON (dockerfile, build context, image name, and the test suite that gates it) and the change-detection path filters.

A lab contributing more than one distinct data collection nests one self-contained directory per project instead, as `labs/suthana/in-lab/` does.
Everything above applies unchanged one level down, and the project's dispatch entry names both parts (`"lab": "suthana"`, `"project": "in-lab"`), which keys it `suthana/in-lab` in `dispatch/sessions.json` and in `dispatch.py --only`.
Labs with a single project stay flat. See `dispatch/README.md` for the field reference.

See "Starting a new conversion" below to have an AI agent do all of this from a description of the lab's data.

## Starting a new conversion

Agent skills for the whole workflow live in `.agents/skills/` (portable [Agent Skills](https://agentskills.io) format; Codex discovers them there natively, and `.claude/skills` symlinks to the same files for Claude Code; see `AGENTS.md`). They cover intake, planning the conversion against the data standard you pick, scaffolding the lab codebase, and registration in dispatch and CI.

To start one, give your agent the default prompt below, filled in:

```text
Please set up a new conversion for the <lab> lab, working through the
new-conversion skills in .agents/skills/ in order: lab-intake, then
lab-conversion-plan, then stop for my review of the plan before running
lab-scaffold and lab-register.

- Lab / PI: <PI name, institution>
- Grant award number: <e.g. R34DA059514>
- Project name: <only if this lab will contribute more than one data collection>
- Incoming dandiset: <six-digit id or https://dandi.emberarchive.org/dandiset/... URL>
- Standardized output dandiset: <six-digit id or URL>
- Data standard: <NWB | BIDS (BEP047) | propose options for my decision>
- Associated papers: <DOIs or links, or "none">
- Source data tree: <verbatim `tree` output of one or more example sessions>
- Metadata: <subject, session, device, and electrode details, or attach files>
- Expected output example: <attach or describe, or "draft one for my review">
- Prior conversion code: <attach scripts + original author names for credit, or "none">
```

Fields you cannot fill yet are fine to leave as "unknown". The intake skill asks about anything that blocks planning and carries the rest forward as `PROVISIONAL`.
