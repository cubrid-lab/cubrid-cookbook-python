# AGENTS.md

## Purpose

`cubrid-cookbook-python` provides use-case-centric, production-style Python examples for CUBRID.

## Read First
- `README.md`
- `docs/internal/PRD.md`
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
- Example content must be written in **English**.
- Use English for GitHub issues, pull requests, and comments; localized documentation is welcome, and no specific tool is required.
- Use `cookbook_` table prefix in all SQL examples.
- Avoid CUBRID reserved words in column names: `value` → `val`, `count` → `cnt`, `data` → `file_data`.
- Use `from __future__ import annotations` in all Python files.
- Use parameterized queries (`?` markers) — never string interpolation.
- If an example's setup or dependencies change, update the surrounding docs in the same change.
- Avoid adding hidden prerequisites that are not documented.

## Development Workflow (cubrid-lab org standard)

All non-trivial work across cubrid-lab repositories MUST follow this 4-phase cycle:

Maintainers coordinate Oracle/Codex reviews, project-specific agent/tool setup,
release classification, labels, and integration. Outside contributors provide
normal motivation, code, tests and docs; no Oracle or agent installation is a
contribution prerequisite. Preserve actual contributor authorship and add tool
attribution only when that tool was used for the commit.

1. **Oracle Design Review** — Consult Oracle before implementation to validate architecture, API surface, and approach. Raise concerns early.
2. **Implementation** — Build the feature/fix with tests. Follow existing codebase patterns.
3. **Documentation Update** — Update ALL affected docs (README, CHANGELOG, ROADMAP, API docs, SUPPORT_MATRIX, PRD, etc.) in the same PR or as an immediate follow-up. Code without doc updates is incomplete.
4. **Oracle Post-Implementation Review** — Consult Oracle to review the completed work for correctness, edge cases, and consistency before merging.

Skipping any phase requires explicit justification. Trivial changes (typos, single-line fixes) may skip phases 1 and 4.

## Agent PR scope and review guardrails

- Before editing, record one acceptance contract, affected files, explicit non-goals
  and the validation plan. Keep each PR to one independently reviewable change.
  Separate contributor guidance, CI configuration and new validator behavior.
- Triage AI findings against that contract, a supported-environment reproduction
  and impact. AI severity is not authority to add capabilities or widen the contract;
  obtain explicit maintainer direction or defer out-of-scope work to a separate issue.
- Batch accepted fixes locally and run relevant checks before publishing a review
  head. Deduplicate agent-initiated review requests by head SHA and review purpose.
- Default to two published AI review rounds total per scoped PR/task: the initial
  review and one corrective re-review. New commits do not reset this budget.
  Further rounds or scope expansion require explicit maintainer direction.
- If unresolved work needs another round at the limit, stop automatic revisions;
  keep the PR Draft and report incomplete work, blockers and a proposed split.
  Never merge with unresolved critical/security defects or failed required CI.
- Maintain one editable, agent-owned English status comment. Avoid bot mentions in
  routine updates, per-finding progress replies and repeated review requests.
  Preserve contributor history; revisit external PRs only after an author-updated head SHA.

## Validation

- `make check` from the repository root (offline contributor checks)
- `make up` (starts CUBRID 11.2 with bounded readiness checking)
- Run the relevant example: `python <file>.py`
- `make verify VERIFY_PATHS=<example-directory>` for matching live goldens
- `make docs` for staged docs and strict MkDocs validation
- `make down` after live checks

Record executed commands/results separately from AI review and checks not run.
Explain gaps; maintainers coordinate the remaining required CI/live validation.

## Commit Convention

Issue titles, pull request titles and commit subjects follow
[CONTRIBUTING.md - Pull request and commit titles](CONTRIBUTING.md#pull-request-and-commit-titles):
`type(scope)!: description` with types `feat`, `fix`, `docs`, `test`, `perf`,
`refactor`, `ci`, `build`, `chore`, `style`, `revert`; English, lowercase start,
no trailing period, no issue numbers in pull request titles (use `Closes #N` /
`Refs #N` in the body). Pull requests are squash-merged and the pull request
title becomes the commit title. The `PR title` check enforces it.

## Issue Labeling (cubrid-lab org standard)

When creating an issue in **any cubrid-lab repository**, assign exactly one
`priority: <value>` label and exactly one `size: <value>` label at creation time,
alongside a type label (`bug`/`enhancement`/`documentation`/`chore`/`ci`/…) and an
`area:` label when applicable. These must be GitHub labels, not just text in the
issue title or body.

Issue titles use the same `type(scope): description` format as pull request
titles (see [CONTRIBUTING.md](CONTRIBUTING.md#pull-request-and-commit-titles)).

Use the following exact names, with **one space after the colon**:

- Priority: `priority: critical`, `priority: high`, `priority: medium`, `priority: low`.
- Size: `size: XS`, `size: S`, `size: M`, `size: L`, `size: XL`.

Do not introduce variants such as `priority:high`, `priority-high`, `P1`, or
`size:S`. Reuse the repository's canonical labels; if a required label is missing,
create it with the exact name above before filing the issue. This policy governs
new issue creation, not bulk renaming or relabeling existing issues unless
explicitly requested.

Maintainers/triagers own label assignment and creation in the authorized filing
or triage workflow. Reporters describe urgency and scope without needing GitHub
label permissions; agents filing for maintainers retain the canonical rules.

Priority reflects urgency and impact; size estimates implementation effort and
helps contributors pick appropriately scoped work.

| Label | Meaning | Rough guide |
|-------|---------|-------------|
| `size: XS` | Trivial change | < ~10 lines; single-file typo/config/one-liner |
| `size: S` | Small change | One file or one focused function; a single test or doc page |
| `size: M` | Medium change | A few files; a new test module, a bug fix with tests, a CI job |
| `size: L` | Large change | Cross-cutting change across many files; multi-artifact (e.g. demo GIF + video + docs) |
| `size: XL` | Very large | Consider splitting into smaller issues before starting |

Rules:

1. **Size reflects effort, not importance** — a one-line fix for a critical bug is still `size: XS`.
2. **Assign both `priority:` and `size:` when filing the issue.** If scope or impact
   is uncertain, use a provisional estimate, explain the uncertainty in the body,
   and add `status: needs triage` (or the repo's equivalent). Refine the estimates
   during triage rather than omitting either required label.
3. **`good first issue` should be `size: XS` or `size: S`.** If a good-first-issue grows
   past `size: S`, re-scope it or drop the `good first issue` label.
4. **`size: XL` is a signal to split**, not a green light to start a sprawling change.

### Good first issue lifecycle

- Unclaimed: `good first issue`.
- A PR is opened for it: remove `good first issue`, add `status: in progress`.
- PR merged: the issue closes.
- PR closed without merging: first check that no other open PR still addresses the issue. Only if none remains, remove `status: in progress` and restore `good first issue`; otherwise keep it in progress.
- Keep 3–5 genuinely unclaimed good first issues per repository; a good first issue should have a small blast radius and an existing pattern or reference PR to follow, not just a small diff.

## Documentation definition of done

Any change that adds, renames, removes, or alters the behavior of an example — or changes supported CUBRID/driver/Python versions — MUST update the matching documentation in the **same PR**. At minimum keep in sync: `SUPPORT_MATRIX.md`, `CHANGELOG.md`, `README.md` (incl. version badges/claims), and any affected `docs/`.

If no documentation change is needed, put a real, nonempty reason on a standalone
`Docs: not needed - <reason>` PR-body line, outside quotes/comments/code fences.
The literal placeholder is not a reason. The existing `docs-not-needed` label is
a maintainer-managed alternative for the docs gate only.

Contributors may request translation help with a language and reason; the request
does not authorize a bypass. Keep Korean synchronization required and community
languages advisory. Only the existing maintainer-approved `translations-deferred`
label skips translation enforcement; maintainers record and own follow-up.

Shared doc-lint/live-smoke callers are pinned to reviewed upstream commits.
Before updating, verify the commit, workflow files and inputs, preserve caller
inputs/permissions/advisory mode, and run checks through a PR. Upstream doc-lint
still downloads its scanner/configuration from main, so the pin is not a claim
that every fetched resource is immutable.

Do not mark work complete until code, tests, and documentation are consistent.

## Project Context

> This repo is the **Python cookbook** for the CUBRID ecosystem.
> Board: [CUBRID Ecosystem Roadmap](https://github.com/orgs/cubrid-lab/projects/2)

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
