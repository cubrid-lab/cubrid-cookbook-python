# AGENTS.md

## Purpose

`cubrid-cookbook-python` provides use-case-centric, production-style Python examples for CUBRID.

## Read First
- `README.md`
- `PRD.md`
- `CONTRIBUTING.md`

## Repository Structure

```
quickstart/        → 5-minute getting-started examples
migration/         → Language migration guides (Java → Python)
templates/         → Copy-and-customize production starters
performance/       → Benchmark-backed optimization patterns
pitfalls/          → Common anti-patterns and fixes
fundamentals/      → Step-by-step reference for core operations
```

## Working Rules

- This is a **Python-only** repository. No Node.js, Go, Rust, or TypeScript content.
- Treat examples as user-facing reference implementations, not throwaway demos.
- All content must be written in **English**.
- Use `cookbook_` table prefix in all SQL examples.
- Avoid CUBRID reserved words in column names: `value` → `val`, `count` → `cnt`, `data` → `file_data`.
- Use `from __future__ import annotations` in all Python files.
- Use parameterized queries (`?` markers) — never string interpolation.
- If an example's setup or dependencies change, update the surrounding docs in the same change.
- Avoid adding hidden prerequisites that are not documented.

## Development Workflow (cubrid-labs org standard)

All non-trivial work across cubrid-labs repositories MUST follow this 4-phase cycle:

1. **Oracle Design Review** — Consult Oracle before implementation to validate architecture, API surface, and approach. Raise concerns early.
2. **Implementation** — Build the feature/fix with tests. Follow existing codebase patterns.
3. **Documentation Update** — Update ALL affected docs (README, CHANGELOG, ROADMAP, API docs, SUPPORT_MATRIX, PRD, etc.) in the same PR or as an immediate follow-up. Code without doc updates is incomplete.
4. **Oracle Post-Implementation Review** — Consult Oracle to review the completed work for correctness, edge cases, and consistency before merging.

Skipping any phase requires explicit justification. Trivial changes (typos, single-line fixes) may skip phases 1 and 4.

## Validation

- `docker compose up -d` (starts CUBRID 11.2)
- Run the relevant example: `python <file>.py`
- Verify output matches expected behavior
- `docker compose down`

## Project Context

> This repo is the **Python cookbook** for the CUBRID ecosystem.
> Board: [CUBRID Ecosystem Roadmap](https://github.com/orgs/cubrid-labs/projects/2)

### Role

cubrid-cookbook-python provides copy-and-run examples for Python developers adopting CUBRID.
All examples must be independently runnable against CUBRID 11.2 via Docker.

### Key Sections

| Section | Purpose |
|---------|---------|
| `quickstart/` | Get running in 5 minutes |
| `migration/java-to-python/` | Side-by-side Java JDBC → Python migration (killer content) |
| `templates/` | Production-ready application starters |
| `performance/` | Benchmark-backed optimization (linked to cubrid-benchmark data) |
| `pitfalls/` | Common mistakes with CUBRID reserved words, auto-commit, etc. |
| `fundamentals/` | Core DB operations: connect, CRUD, transactions, ORM |
