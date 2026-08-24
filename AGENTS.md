# Agent instructions

Instructions for AI coding agents working in this repository, whatever the tool (Claude Code, Codex, or others). `CLAUDE.md` is a symlink to this file, so Claude Code loads the same instructions natively.

## Commits and PRs

- Always run `pre-commit` before committing and pushing changes
- Always link PRs to issues when possible
- PR titles should be human-readable and in the past tense. They should NOT use conventional commit style.
- Keep PR descriptions as short and concise as possible: the fewest words that describe the change accurately
- End every PR description with a `<details>` dropdown holding the prompts that asked for the work, quoted verbatim and in order: the original request first, then each follow-up as the branch grows. The prose above it stays a description of the change, not of the conversation
- Every commit must include a `Co-Authored-By` trailer identifying your tool name and version and your underlying model and version. Format (replace all `<…>` placeholders with actual values): `Co-Authored-By: <Tool> <tool-version> / <Model> <model-version> <noreply@vendor-domain>`

## Code style

- Require keyword-only arguments `(*, ...)` for multi-input functions. For any function with exactly one caller-supplied parameter (excluding `self` and `cls`), require positional-only usage with the `/` designator.
- Always add new imports at the top of the file. The only exception is when a local import is needed to avoid a circular dependency.
- For external dependencies, use the full module import style (e.g., `import xyz; xyz.abc`) rather than `from xyz import abc`.
- For internal imports, always use relative style (e.g., `from .foo import bar`).
- Prefer assigning return values to named locals before `return` when this improves readability and debugger breakpoint placement.
- Avoid excessive em-dashes, colons, and semicolons in written text such as documentation. Prefer breaking into separate, shorter sentences instead.
- Favor defining one-word names for CLI flags, then map those onto longer, more explicit keyword arguments at the API level.
- Keep inline comments sparse. Only explain non-obvious "why", not "what" the code does. Prefer self-documenting code and clear names over narration; do not annotate routine logic.

## Tests

- To the best of your ability, ensure tests are passing before pushing
- Follow assertion style: actual on left, expected on right
- Always mark AI-generated tests with the `ai_generated` pytest marker
- Use `pytest.mark.parametrize` wherever appropriate to reduce duplication in test cases

## Skills

- Reusable agent skills live under `.agents/skills/`, one directory per skill, in the open [Agent Skills](https://agentskills.io) format: a `SKILL.md` with `name` and `description` frontmatter, plus a `references/` directory where needed. Codex discovers repository skills at that path natively. `.claude/skills` is a symlink to the same directory so Claude Code picks them up too. Any other tool can simply read the `SKILL.md` whose description matches the task and follow it, loading its reference files when it says to.
- When a task matches a skill's description, read its `SKILL.md` and follow it, even if automatic skill discovery did not surface it.

### The new-conversion skills

Setting up a new lab or project runs through these skills, in order:

1. `lab-intake` normalizes the provided description (papers, source-data tree, metadata, target standard, dandiset ids, prior scripts) into a structured intake record, and starts the verbatim prompt record under `labs/<lab>/prompts/`.
2. `lab-conversion-plan` pins down the requester's data-standard decision (NWB, or BIDS BEP047) and drafts the source-to-output mapping plus an example of how the expected output appears, for sign-off before any code is written. The requester owns the strategy. The plan exists so the scripts get written correctly.
3. `lab-scaffold` builds the self-contained `labs/<lab>/` codebase following the established layout.
4. `lab-register` wires the lab into the dispatch registries, CI, and the READMEs.
5. `lab-lessons` closes the loop: what the conversion taught gets generalized back into these skills, with strategy-level changes marked for the requester's sign-off. The skill set is expected to improve with every conversion.

The top-level `README.md` section "Starting a new conversion" holds the default prompt developers use to kick this off.

### External skills

- `.agents/vendor/claude-skills` is a git submodule of [catalystneuro/claude-skills](https://github.com/catalystneuro/claude-skills), tracking `main` (shallow). Only its `nwb-convert` skill is exposed to discovery, via the `.agents/skills/nwb-convert` symlink. It carries deep NWB conversion know-how (NeuroConv and PyNWB usage, data inspection, synchronization, metadata phases).
- A fresh clone starts with the submodule empty. Initialize it with `git submodule update --init`, or fetch the latest upstream `main` with `git submodule update --init --remote`. Refresh before relying on nwb-convert, since the committed pin is only where it was last bumped.
- Refreshing with `--remote` changes the recorded pin in the working tree. Commit that bump deliberately, on its own or as part of closing out a conversion, not as a stowaway in an unrelated commit.
- External skills are guidance, not authority. Where nwb-convert's instructions differ from this repository's conventions (for example, it builds standalone pip-installable repos, while conversions here live in `labs/<lab>/`), this file and the lab skills win.
