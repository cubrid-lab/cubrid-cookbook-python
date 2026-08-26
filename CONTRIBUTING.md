# Contributing to cubrid-cookbook-python

Thank you for your interest in contributing! This document provides guidelines
and instructions for contributing to the project.

## Table of Contents

- [Development Workflow](#development-workflow)
- [Adding Examples](#adding-examples)
- [Code Style](#code-style)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Reporting Issues](#reporting-issues)

---

## Development Workflow

All non-trivial work follows the cubrid-lab 4-phase cycle. Every change to an
example ships its implementation, its tests, and its docs **together** — code
without doc updates is considered incomplete.

1. **Design review** — Validate the approach and API surface before building.
2. **Implementation** — Build the feature/fix with tests, following existing patterns.
3. **Documentation update** — Update ALL affected docs (README, SUPPORT_MATRIX,
   CHANGELOG, ROADMAP) in the same PR. A new, renamed, or removed example must be
   reflected in README.md.
4. **Post-implementation review** — Review the completed work for correctness and
   consistency before merge.

Trivial changes (typos, single-line fixes) may skip phases 1 and 4.

This rule is enforced in CI by `scripts/check_docs_sync.py` (the **Docs sync
gate** job). The gate fails when an example directory is missing from README.md,
and warns when an example ships no `expected/` golden file or `tests/` suite.
Run it locally before opening a PR:

```bash
python3 scripts/check_docs_sync.py
```

Intentional coverage exceptions live in `scripts/docs-sync-allowlist.txt` with a
recorded reason.

---

## Adding Examples

### Guidelines

1. **Every example must work** — verify against a live CUBRID instance before submitting
2. **Prefix all table names** with `cookbook_` to avoid conflicts
3. **Include a README** for each example with setup and run instructions
4. **Follow the existing directory structure**:

```
quickstart/          # 5-minute getting-started examples
fundamentals/        # Core CUBRID operations with Python
templates/           # Production-ready application templates
migration/           # Language migration guides (Java → Python)
performance/         # Benchmark-backed optimization patterns
pitfalls/            # Common mistakes and fixes
docs/                # Internal docs (PRD, agent playbook)
```

### Running Examples

```bash
# Start CUBRID
docker compose up -d

# Example: run a FastAPI template
cd templates/api-service-fastapi
pip install -r requirements.txt
uvicorn app:app --reload

# Example: run a fundamental
python fundamentals/pycubrid/01_connect.py
```

### Golden Verification

Runnable examples are checked against committed golden output with `make verify`,
which discovers each committed `<dir>/expected/<name>.expected`, runs the matching
`<dir>/<name>.py`, pipes it through `scripts/normalize_output.sh`, and diffs the
result against that golden file. When you add a one-shot example, capture its
golden output so CI can guard it.

This is enforced: `scripts/check_expected_coverage.py` (run by `make verify` and
the smoke-test workflow) fails if any runnable `<dir>/*.py` inside a directory
that owns an `expected/` folder has no matching `expected/<name>.expected`
golden. To opt a script out, add it to `scripts/verify_exclusions.txt` with a
reason — but prefer making the example deterministic and adding a golden.

#### Excluded from golden verification

Some examples are **intentionally** outside `make verify`. They are still real,
runnable examples — they just can't be captured as a deterministic one-shot
golden. If you see one of these without an `expected/` file, that is expected
and not missing coverage:

| Example | Why it is excluded |
|---------|--------------------|
| `quickstart/5min-fastapi` | Long-lived ASGI web service (`uvicorn`) exercised via HTTP, not a deterministic one-shot script — it runs until stopped, so there is no single terminal output to golden-capture. |
| `templates/async-worker` | Celery worker that requires an external broker (Redis) and runs until stopped. |
| `performance/bulk-insert/benchmark.py` | Throughput benchmark — prints wall-clock timings and rows/sec that vary run-to-run. |
| `performance/connection-pooling/benchmark.py` | Throughput benchmark — timings and speedup factors are nondeterministic. |
| `performance/fetch-optimization/benchmark.py` | Throughput benchmark — per-strategy timings are nondeterministic. |

Where output is dynamic only in *presentation* (timings, absolute paths, peak
memory), prefer adding a presentation-only rule to `scripts/normalize_output.sh`
(see `make test-normalize`) so the example can be golden-captured instead of
excluded. Reserve exclusion for examples that never produce deterministic,
one-shot terminal output.

---

## Code Style

### Python

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

- **Line length**: 100 characters
- **Target Python**: 3.10+
- **Formatter**: `ruff format`
- **Linter**: `ruff check`

```bash
# Check lint
ruff check .

# Auto-fix lint issues
ruff check --fix .

# Check formatting
ruff format --check .

# Apply formatting
ruff format .
```

---

## Pull Request Guidelines

### Before Submitting

1. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/my-example main
   ```

2. **Verify your example works** against a live CUBRID instance:
   ```bash
   docker compose up -d
   # Run your example and confirm it works
   ```

3. **Run lint checks** on Python code:
   ```bash
   ruff check .
   ruff format --check .
   ```

### PR Content

- Keep PRs focused — one example or fix per PR.
- Write a clear title and description explaining _what_ and _why_.
- Reference any related issues (e.g., `Fixes #42`).
- Include output demonstrating the example works.

### Review Process

- All PRs require at least one review before merge.
- CI must pass (lint checks).
- Examples must be tested against a live CUBRID instance.

---

## Reporting Issues

When reporting a bug in an example, please include:

- Which example you're running
- Python version
- CUBRID server version
- Full error output
- Steps to reproduce

For new example requests, describe the use case and framework.

---

## Questions?

Open a [GitHub Discussion](https://github.com/cubrid-lab/cubrid-cookbook-python/discussions)
or file an [issue](https://github.com/cubrid-lab/cubrid-cookbook-python/issues).
