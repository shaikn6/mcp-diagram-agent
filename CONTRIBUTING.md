# Contributing to MCP Diagram Agent

Thank you for considering a contribution! This project follows a straightforward
workflow to keep the codebase clean and well-tested.

## Development Setup

```bash
# 1. Clone and enter the repo
git clone https://github.com/shaikn6/mcp-diagram-agent.git
cd mcp-diagram-agent

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install with dev extras
pip install -e ".[dev]"

# 4. Copy the env template
cp .env.example .env
# Set your ANTHROPIC_API_KEY in .env
```

## Running Tests

```bash
# All tests with coverage
pytest

# A single file
pytest tests/test_diagram_generator.py -v

# Skip coverage requirement (faster iteration)
pytest --no-cov -v
```

## Linting & Formatting

```bash
ruff check src/ tests/       # lint
ruff format src/ tests/      # auto-format
mypy src/                    # type check
```

## Pull Request Guidelines

1. **One concern per PR.** Bug fix, feature, or refactor — not all three.
2. **Tests are required.** New code needs unit tests; 80% coverage minimum.
3. **Follow Conventional Commits** for the PR title: `feat:`, `fix:`, `docs:`,
   `refactor:`, `test:`, `chore:`, `perf:`.
4. **No secrets** — never commit `.env` or API keys.
5. The CI pipeline (lint → type-check → test → docker build) must be green.

## Adding a New Diagram Layer / Element Type

1. Add the new `ElementType` value to `src/models.py`.
2. Update `color_for_layer()` in `src/utils.py` if it's a new semantic layer.
3. Update `_build_elements()` in `src/diagram_generator.py`.
4. Add/update tests in `tests/test_diagram_generator.py`.
5. Update the `_SYSTEM_PROMPT` in `diagram_generator.py` to teach Claude about
   the new type.

## Reporting Bugs

Use the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.md).

## Requesting Features

Use the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.md).
