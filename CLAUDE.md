# CLAUDE.md

Guidance for Claude Code (and other AI coding agents) working in this repository.

## Mark AI-generated tests

Every test authored (fully or mostly) by an AI coding agent must carry the `ai_generated` pytest marker.
Add `pytestmark = pytest.mark.ai_generated` near the top of the test module (after the imports), rather than decorating each test function individually, unless a module mixes AI-generated and human-written tests, in which case decorate only the AI-generated ones with `@pytest.mark.ai_generated`.

```python
import pytest

pytestmark = pytest.mark.ai_generated


def test_something():
    ...
```

The marker is registered repo-wide in the root `pyproject.toml` (`[tool.pytest.ini_options]`), so it applies to `dispatch/tests/`, every `labs/<lab>/tests/`, and any tests added later — register new test suites against that same config rather than adding a competing pytest config elsewhere in the repo.
