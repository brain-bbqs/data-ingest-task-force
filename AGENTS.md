# Agent instructions

Instructions for AI coding agents working in this repository, whatever the tool (Claude Code, Codex, or others).

- `CLAUDE.md` at the repo root holds the repository-wide conventions: commit and PR rules, code style, and test rules. They apply to every agent and every tool, not only Claude. Read it before making changes.
- Reusable agent skills live under `.agents/skills/`, one directory per skill, in the open [Agent Skills](https://agentskills.io) format: a `SKILL.md` with `name` and `description` frontmatter, plus a `references/` directory where needed. Codex discovers repository skills at that path natively. `.claude/skills` is a symlink to the same directory so Claude Code picks them up too. Any other tool can simply read the `SKILL.md` whose description matches the task and follow it, loading its reference files when it says to.

## The new-conversion skills

Setting up a new lab or project runs through four skills, in order:

1. `lab-intake` normalizes the provided description (papers, source-data tree, metadata, target standard, dandiset ids, prior scripts) into a structured intake record, and starts the verbatim prompt record under `labs/<lab>/prompts/`.
2. `lab-conversion-plan` pins down the requester's data-standard decision (NWB, or BIDS BEP047) and drafts the source-to-output mapping plus an example of how the expected output appears, for sign-off before any code is written. The requester owns the strategy. The plan exists so the scripts get written correctly.
3. `lab-scaffold` builds the self-contained `labs/<lab>/` codebase following the established layout.
4. `lab-register` wires the lab into the dispatch registries, CI, and the READMEs.

The top-level `README.md` section "Starting a new conversion" holds the default prompt developers use to kick this off.
