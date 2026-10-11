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

Select the review route by the tool that **actually developed** the change.
Record that route in the PR; a pending review request, green CI, self-review
or automated "approval recommended" summary is not a completed review.

**OpenCode with Oracle**, for non-trivial work:
1. Obtain Oracle **design review** of scope and approach before implementation.
2. Implement the agreed change with focused tests and live example evidence
   where the existing policy requires it.
3. Update only affected documentation under the existing documentation definition
   of done, including README, SUPPORT_MATRIX, CHANGELOG and example docs when
   applicable. Keep the existing docs-not-needed process for unaffected docs.
4. Obtain Oracle **post-implementation review**, address material findings
   and record both Oracle outcomes and test results.

Trivial OpenCode typo/single-line work may omit Oracle phases 1 and 4 only with
a recorded reason. Both Oracle reviews satisfy this tool-specific route;
additional GitHub Copilot review is not automatically required. Existing CI,
maintainer/repository checks and live-CUBRID rules still apply.

**Standalone agents (Claude Code, Codex, ChatGPT, or other agent tools):**
implement and test, open a PR, then **wait for a substantive submitted GitHub
Copilot review or another person's review** before merging. A submitted
COMMENTED review with an actual assessment counts as evidence but is not formal
APPROVED status. Requested/pending review, a boilerplate approval suggestion,
self-review or CI success does not qualify.
Validate accepted fixes at the final relevant head; leave the PR unmerged if
the required review has not arrived.

**Human contributions:** follow the normal PR and review process. This route
is not a fallback for unnamed standalone agent tools, which use the route above.
No OpenCode, Oracle, Copilot, Claude Code or Codex installation is a contribution
prerequisite. Maintainers coordinate internal review tools, assignments,
integration and release decisions. Preserve authorship and credit tools only
when they actually produced the work.

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

## Review disposition and merge evidence

- Record the development route, reviewer/Oracle evidence, relevant reviewed
  head SHA and pending/complete status in the PR.
- Triage each actionable review finding as fixed (commit and focused tests),
  rejected (specific contract/reproduction reason), or deferred (linked issue).
  Do not expand a recipe's behavior merely because an AI suggested it.
- Reply once with **final** disposition in each relevant inline review thread.
  A reviewer or maintainer resolves a thread only after checking the updated
  source and evidence. An outdated diff or reply is not an automatic resolution;
  never bulk-resolve old threads without checking.
- Maintain one editable agent-owned English PR status comment with the overall
  state, required CI/live checks, checks not run, and outstanding findings.
  Avoid repeating whole test logs and prompting the same bot on each thread.
- Keep the existing two published AI-review rounds budget; further rounds need
  maintainer direction. If no qualifying review arrives or a serious issue
  remains, keep the PR Draft/unmerged and report the pending work.
- Before merging check the applicable review route, final source, required CI
  and live evidence where required by the existing validation policy. Never
  merge unresolved critical/security issues or failed required checks.
  Nonblocking open findings need explicit maintainer disposition. This does
  not change bot automerge or GitHub protection settings.

## Issue specification and ownership

- An issue body is the current work specification, not a session transcript. Keep
  it current; put dated progress, pause and review outcomes in comments, and
  preserve historical evidence together with its limits.
- For non-trivial work capture the applicable fields: problem/impact, evidence with
  revision/environment, reproduction or investigation question, expected behavior,
  scope and non-goals, relevant files, completion criteria, validation and actual
  dependencies. Small docs/example tasks use only the fields that apply.
- GitHub Assignees are the source of truth for implementation ownership. Set the
  actual implementer in Assignees before implementation starts; comments or claim
  messages alone do not replace assignment. Agree and record a handoff before
  changing ownership, and unassign when returning unfinished work.
- Before closing, preserve contributor evidence and open PRs, and recheck stale
  dependency/checklist state.

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
`refactor`, `ci`, `build`, `chore`, `style`, `revert`; English, lowercase start
unless the first word is an API name, acronym, or proper noun; no trailing
period, no issue numbers in pull request titles (use `Closes #N` /
`Refs #N` in the body). Pull requests are squash-merged and the pull request
title becomes the commit title. The `PR title` check enforces it.

## GitHub Release Policy

This repository currently publishes no GitHub Releases, and no release automation is
added. If Releases are introduced later, these rules apply unchanged.

### Titles

- A Release title equals its tag exactly. Stable tags and titles are `vMAJOR.MINOR.PATCH`.
- No package name, feature, date or suffix in a title (not `cubrid-cookbook-python 1.2.3`,
  `v1.2.3 — Foo`, `v1.2.3 (corrected)` or `Release v1.2.3`). Drafts follow the same rule.
- Never move, delete or recreate a tag to fix a title. Never delete and recreate a
  published Release.
- Metadata edits keep the notes, assets, published state and prerelease state. When
  editing a draft through the API, always resend `tag_name`: a PATCH without it resets
  the draft's tag to `untagged-…`. `gh release edit` resends `tag_name` automatically;
  raw `gh api` PATCHes must include it.
- Agents verify these rules whenever they touch release automation.

### Stale drafts

- Inspect drafts before preparing a release. Never assume a draft is pending.
- Classify each draft against its tag:
  - Already shipped (the tag exists): publish it with `make_latest=false`, or remove
    it, only after maintainer approval.
  - Never shipped: never publish it. Delete it only after maintainer approval.
- Never delete drafts automatically. Preserve their notes and assets.

### Release notes

- `CHANGELOG.md` is the single source of truth. The Release body is the extracted
  CHANGELOG section plus one `**Full Changelog**` compare link.
- Allowed `###` sections, in this order, only when they have content: Upgrade notes,
  Added, Changed, Deprecated, Removed, Fixed, Security, Performance, Documentation, CI,
  Tests. `scripts/lint_changelog.py` enforces this for `[Unreleased]` and for releases
  after 0.2.0.
- Use `Documentation`, not `Docs`. Put release automation and tooling entries under
  `CI` or `Changed`.
- Never bulk-rewrite historical notes or regenerate them from current `main`. A
  selective fix needs a dry-run diff and maintainer approval. Never invent PR or commit
  references. Note formatting never changes tags, dates, artifacts or publish state.

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

Maintainers/triagers own label policy and assignment. An authorized agent filing
or triaging on a maintainer's behalf may apply the canonical labels above. Outside
reporters describe urgency and scope without needing GitHub label permissions.

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
- Keep at least 3 genuinely unclaimed good first issues per repository; a good first issue should have a small blast radius and an existing pattern or reference PR to follow, not just a small diff.
- Do not implement a `good first issue` unless a maintainer explicitly authorizes that **specific issue**; broad backlog, review or release instructions are not permission.
- Release/blocker handoff of a good first issue requires explicit maintainer action after checking assignees, comments and open PRs.

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
