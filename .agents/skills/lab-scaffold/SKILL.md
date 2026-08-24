---
name: lab-scaffold
description: Build the self-contained labs/<lab>/ codebase for an approved BRAIN-BBQS conversion, following this repository's established layout of code/, containers/, envs/, tests/, prompts/, and README.md. Use it whenever someone asks to scaffold, implement, build, or port a conversion pipeline for a new lab or project, after lab-conversion-plan has been signed off. Covers both writing a converter from scratch and porting previously written conversion scripts verbatim with provenance and author credit. Follow with lab-register to wire the lab into dispatch and CI.
---

# Lab scaffold

Build `labs/<lab>/` (or `labs/<lab>/<project>/` for a multi-project lab) as a self-contained codebase, matching the approved conversion plan. Self-contained means the directory carries its own conversion code, tests, environment declaration, and container, so labs evolve independently.

Do not start without a signed-off plan from lab-conversion-plan. The plan supplies the mapping, the identity rules, the expected output, and the metadata skeleton this skill turns into code.

## The layout contract

| Path | Purpose | Canonical examples |
| --- | --- | --- |
| `code/` | Converter, batch driver, `config.yaml`, `code/README.md` | `labs/inman/code/`, `labs/kemere/code/` |
| `containers/<name>.Dockerfile` | The pinned, reproducible runtime (environment only) | `labs/inman/containers/` |
| `envs/pyproject.toml` | Loose, unpinned environment declaration with a `[test]` extra | `labs/inman/envs/` |
| `tests/` | One golden-file integration test plus committed fixtures | `labs/kemere/tests/` |
| `prompts/` | Verbatim AI-agent prompts, started by lab-intake | `labs/kemere/prompts/` |
| `README.md` | The lab's own README | `labs/kemere/README.md`, `labs/shepherd/README.md` |

`references/layout-contract.md` specifies each piece file by file, including the dispatch contract the batch driver must satisfy, the naming rules derived from the grant award number, and the verbatim-port rules. Read it before writing anything.

## Build order

1. `code/config.yaml` from the plan's metadata skeleton, every unconfirmed value marked `PROVISIONAL`.
2. The core converter, implementing the plan's mapping and identity rules exactly. Out-of-scope files are reported, not silently skipped. For NWB converters, first refresh and read the vendored `nwb-convert` skill (`.agents/skills/nwb-convert`, see the external-skills section of `AGENTS.md`) for NeuroConv and PyNWB practice. Its repo-generation workflow does not apply here, the layout contract does.
3. The batch driver that dispatch will run (skip it only if the core converter already processes a whole incoming dandiset in one invocation, as kemere's does).
4. `envs/pyproject.toml`, then the Dockerfile that resolves it.
5. Tests with committed `example_raw/` and `expected_output/` fixtures, plus `generate_fixtures.py`.
6. `code/README.md` and the lab `README.md`, folding in the intake facts and the plan.

## Repository conventions that apply here

- Everything in the repo `AGENTS.md`: keyword-only arguments, import style, sparse comments, assertion order, the `ai_generated` pytest marker, `pytest.mark.parametrize` where it reduces duplication.
- Run `pre-commit run --files <new files>` and the lab's pytest suite before handing off. Formatting is black + ruff at line length 120, configured at the repo root.
- Committed fixtures that must stay byte-exact get excluded from the formatters in `.pre-commit-config.yaml` and from ruff in the root `pyproject.toml`. Follow the existing exclusion patterns in both files.
- Unconfirmed metadata stays visibly `PROVISIONAL` in `config.yaml` and gets a "replace before treating output as final" note in the lab README.

## Porting existing conversion scripts

When the intake says prior scripts exist, the port mode from the intake decides the treatment:

- Verbatim as provenance (shepherd precedent): byte-for-byte apart from a short provenance note at the top naming the original author. Add the files to the formatter and linter exclusions. Document every known rough edge in the lab README instead of fixing it, so the follow-up has a starting point and nobody trusts the output prematurely. New code alongside the port (a batch driver, tests) gets the normal treatment.
- Improve on the way in (inman precedent): normal treatment, but the original author is still credited in the lab README and the port is kept reviewable.

Either way, credit the original author by name in the lab README ("originally authored by ...").

## Definition of done

- [ ] Layout matches the contract table, nothing extra at the lab root
- [ ] Batch driver satisfies the dispatch contract in `references/layout-contract.md`
- [ ] `pre-commit` clean and the lab's pytest suite green
- [ ] `config.yaml` carries no unmarked guesses
- [ ] Both READMEs written, prompts record current
- [ ] Ported files, if any, credited and excluded per the port mode

Then continue with the lab-register skill to wire the lab into dispatch and CI.
