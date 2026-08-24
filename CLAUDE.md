# Agent instructions

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

## Skills

- Reusable agent skills live in `.agents/skills/` (`.claude/skills` is a symlink to it, see `AGENTS.md`). When a task matches a skill's description, read its `SKILL.md` and follow it, even if automatic skill discovery did not surface it.

## Tests

- To the best of your ability, ensure tests are passing before pushing
- Follow assertion style: actual on left, expected on right
- Always mark AI-generated tests with the `ai_generated` pytest marker
- Use `pytest.mark.parametrize` wherever appropriate to reduce duplication in test cases
