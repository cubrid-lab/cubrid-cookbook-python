# AGENTS.md

## Organization-wide issue and PR writing standard

Follow [the shared cubrid-lab policy](https://github.com/cubrid-lab/.github/blob/main/docs/ISSUE_PR_COMMIT_STANDARD.md). Use type-only Issue titles (`feat: ...`, `bug: ...`, `docs: ...`) **without a required module scope**. Describe the problem or desired result in readable English and document observable acceptance criteria, distinguishing reproduced facts from assumptions. Triage decides validity, duplicates, priority and size. PRs and commits keep their existing Conventional Commits/CI rules; do not turn issue-body prose into agent narration or personal comments.


## Purpose

`cubrid-cookbook-python` provides use-case-centric, production-style Python examples for CUBRID.

## Read First
- `README.md`
- `docs/internal/PRD.md`
- `CONTRIBUTING.md`

## Repository Structure

```
quickstart/        → 5-minute getting-started examples
migration/         → Migration guides (Java → Python, CUBRIDdb → pycubrid)
templates/         → Copy-and-customize production starters
performance/       → Benchmark-backed optimization patterns
pitfalls/          → Common anti-patterns and fixes
fundamentals/      → Step-by-step reference for core operations
demos/             → Recording scripts and provenance for the README demo media
docs/              → MkDocs site sources, translations and internal design notes
scripts/           → CI, docs, golden-output and release-verification helpers
tests/             → Repository-wide tests and CI checks (recipe tests live beside examples)
```

Example counts and tested versions change often; `README.md` and
[`SUPPORT_MATRIX.md`](SUPPORT_MATRIX.md) are authoritative.

## Working Rules

- This is a **Python-only** repository. No Node.js, Go, Rust, or TypeScript content.
- Treat examples as user-facing reference implementations, not throwaway demos.
- Example content must be written in **English**.
- Use English for GitHub issues, pull requests, and comments; localized documentation is welcome, and no specific tool is required.
- Use `cookbook_` table prefix in all SQL examples.
- Avoid CUBRID reserved words in column names: `value` → `val`, `count` → `cnt`, `data` → `file_data`.
- Use `from __future__ import annotations` in new Python modules. Some existing FastAPI,
  Flask and Django template modules omit it; treat those as legacy module-level
  exceptions, not a pattern to copy.
- Use parameterized queries (`?` markers) — never string interpolation.
- If an example's setup or dependencies change, update the surrounding docs in the same change.
- Avoid adding hidden prerequisites that are not documented.

## Development Workflow (cubrid-lab org standard)

The same review and merge criteria apply to human-authored work and code
produced with OpenCode, Codex, Claude Code, ChatGPT, Copilot or other tools.
AI design/post reviews and specific Copilot approval routes are never required
solely because of the tool used.

1. Keep the PR focused with tests and affected documentation. Explain when
   documentation updates are unnecessary.
2. Treat required GitHub Actions CI on the final head as the authoritative
   result. Preserve `make check test`, docs, and applicable live CUBRID
   verification. Local runs are encouraged but not a separate merge gate.
3. Review correctness, test coverage, maintainability, regression impact
   and security. Oracle, Copilot and `agent-review` are optional **advisory**
   evidence, not GitHub approval or a mandatory review stage.
4. Address or disposition findings and let the responsible maintainer make
   the final merge decision after required CI. Retain independent review for
   high-impact workflow permissions, protected release verification and
   publishing paths.

Do not relax code ownership routing, fork workflow safety, live validation
or the repository's required GitHub branch checks.

## Agent PR scope and review guardrails

Apply these guardrails to every implementation tool:
- Define acceptance criteria, affected files, non-goals and validation before
  substantial work. Preserve a focused, independently reviewable scope.
- Triage AI findings against actual behavior and impact; never expand
  requirements just because an AI report assigns a severity.
- AI review rounds are optional. Avoid duplicate bot requests, preserve
  contributor history, and seek re-review after relevant source updates.
- Never merge with unresolved critical/security defects or failed required CI.

## Review disposition and merge evidence

- Record the final reviewed head, required GitHub CI/live results, checks
  not run, material risks, findings and responsible maintainer decision.
- Fix and verify actionable defects, reject unsupported findings with
  reasons, or track genuinely separate follow-ups as local issues.
- Leave one final disposition reply per relevant thread; a reviewer or
  maintainer verifies the updated source before resolving it.
- If an agent contributes, keep concise status rather than repeated bot
  rounds; Oracle/Copilot/`agent-review` are always advisory.
- Before merging, verify final code, branch checks and independent approval
  on protected/security-sensitive paths where the project requires it.

## PR overlap and execution precedence

- Before opening a PR, check the linked issue's accepted scope and
  dependencies, other open PRs, and work merged into `main` since the branch
  was created. Mark relevant `Supersedes #N`, `Depends on #N` or
  `Parallel to #N` with a reason; otherwise write `None`.
- Pick a canonical PR by behavior, focused scope, test evidence and maintainer
  direction. Recheck before merging; neither a newer PR nor green CI overrides
  an unmet prerequisite, incomplete golden/live evidence or a protected
  workflow/release review.
- In the same review cycle after merging, explain and close truly superseded
  PRs or record why parallel work stays valid. Update linked issues and do not
  declare parent acceptance complete merely because sub-PRs merged. Keep
  contributor history and coordinate external work.
- After a policy change, reconcile contradictory older instructions in active
  issues/PRs and templates, or leave a narrow documented follow-up.
- `priority:` records urgency, `size:` effort; actual execution order also
  depends on readiness, verification and maintainer release decisions. Preserve
  the already-live `make verify` contract and do not redo merged Compose work.
  No additional automation, check or organization-level tracker is required.

## Issue specification and ownership

Issues and implementation acceptance are repository-local: file work in the
repository whose code, workflow, or documentation must change. Each repository
owns its scope, priority, assignee, validation, release decision and closure.
Every issue must be understandable without opening another repository's issue.
When several repositories need changes, create a separate, self-contained issue
and PR in each repository. Never use an issue here as an organization-wide
tracker, a shared implementation contract or an approval gate for other projects.
Link another repository's issue only when its concrete technical behavior is
essential evidence for local reproduction or verification; do not cross-link
implementation issues by default or inherit another repository's acceptance
criteria, ownership or closure requirements.

Before publishing or editing an issue, inspect its title and full body:
- Describe this repository's problem, evidence, affected files and actual Make
  targets, expected behavior and checkable completion criteria.
- Exclude contest/judging, assessment, submission, presentation rehearsal,
  evaluation-tag/SHA freezes and event-timed implementation gates. Commit or
  release identifiers belong only where needed to reproduce technical behavior.
- Do not invent `make spec-*` targets, assume a sibling project's commands apply
  here or prescribe a universal command/report format without checking this
  repository's Makefile and CI.
- Search for duplicate issues and conflicting target semantics before posting;
  reread the saved title/body and correct misplaced scope or references.
Never use issue auto-closing keywords with another repository's issue; its
maintainer controls closure. The existing required PR title check rejects
direct foreign-repository closing references in the PR body, the PR title and
commit messages while allowing Refs links. `main` is squash-merged with the PR
title and the commit messages; an edit to the squash message at merge time is
not checked, so do not add foreign closing keywords there.

- An issue body is the current work specification, not a session transcript. Keep
  it current; put dated progress, pause and review outcomes in comments, and
  preserve historical evidence together with its limits.
- For non-trivial work capture the applicable fields: problem/impact, evidence with
  revision/environment, reproduction or investigation question, expected behavior,
  scope and non-goals, relevant files, completion criteria, validation and actual
  dependencies. Small docs/example tasks use only the fields that apply.
- For maintainer-operated autonomous agents and internally assigned work, maintainers must set the actual implementer in GitHub Assignees before implementation. Comments alone are not a substitute for this agent assignment; autonomous agents also need explicit issue-specific authorization to take a `good first issue`.
- Human-led outside contributors (including those using AI assistance under their direction) may work on an unclaimed issue and open a PR without prior approval or Assignee permissions. Check active assignments, comments, and PRs; an interest comment is encouraged but optional. Do not silently take over another contributor's claimed work.
- Maintainers own assignment updates, handoffs and issue labels; preserve contributor evidence and coordinate release-blocker handoffs.
- Before closing, preserve contributor evidence and open PRs, and recheck stale
  dependency/checklist state.

## Validation

- `make check test` from the repository root (offline contributor checks, as CI runs them; the
  documented pre-PR command, `make check` stays contributor-facing as part of it)
- Standard sequence: `make test` (offline), then `make verify` (complete live validation); the
  focused lanes below are advanced / debugging lanes and print `PARTIAL`
- `make check` (non-test quality gate: `lint`, `format-check`, `check-docs`, `check-coverage`;
  changes no file); `make format` is the only target that rewrites files
- `make test` (every offline suite, including `test-normalize`; no database or Docker;
  `make test-offline` is an alias; suite list in `scripts/run_offline_tests.py`)
- `make docker-up` (alias `make up`; starts the Compose service `cubrid` with CUBRID 11.2 by default,
  `CUBRID_VERSION=11.4` to override, with bounded readiness checking)
- `make deps` (installs the drivers, pytest and every example's requirements)
- Run the relevant example: `python <file>.py`
- `make verify-goldens VERIFY_PATHS=<example-directory>` for matching live goldens (a partial
  check; `make verify` refuses `VERIFY_PATHS`)
- Advanced / debugging: a focused live lane (`make verify-quickstart`, `verify-performance`, `verify-web`,
  `verify-django-celery`, `verify-ai-agent`, `verify-dashboard`) or the full `make verify`
  (every golden and live suite; needs dedicated `CUBRID_TEST_URL` and
  `CUBRID_DASHBOARD_TEST_URL` databases, see CONTRIBUTING.md "Live verification")
- `make docs` for staged docs and strict MkDocs validation
- `make docs-check` for links, anchors and recipe commands in every Markdown file (pinned tools: `.github/requirements-docs-check.txt`)
- `make docker-down` (alias `make down`) after live checks (keeps the data; `make clean` removes
  only generated files and caches, and `make docker-clean` is the one target that deletes the
  lab's volumes)

Record executed commands/results separately from AI review and checks not run.
Agent benchmark tasks and their offline grader live in
[`agent-evals/`](agent-evals/README.md) (`make agent-eval-check`); they never replace
the checks above. Their frozen fixtures and historical revisions apply **only**
to optional agent evaluations, not ordinary recipe issues or PR merge criteria.
Never claim an offline score or a partial golden lane proves a live, complete
`make verify` run. Explain gaps; maintainers coordinate the remaining
required CI/live validation.

## Commit Convention

Pull request titles and commit subjects follow
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

## Issue triage lifecycle

Every new issue here starts with `status: needs triage`; templates attach the
label, while the `issues: opened` workflow covers other user submissions.
Automation using `GITHUB_TOKEN` must include it on issue creation since
those events may not trigger a subsequent workflow.

1. Verify problem, evidence and unknowns, duplicate/open-PR overlap, correct
   repository/type, scope/non-goals, acceptance criteria and prerequisites.
   Close a duplicate or invalid issue with an explicit reason.
2. Compare with **the full current open-issue list in this repository**,
   following pagination. Weigh effect on users, security, active work,
   priority labels, and ready versus blocked dependencies. Record a reason
   when changing another issue's priority; do not rank by number or age.
3. Apply exactly one `priority: critical/high/medium/low` and one of the
   existing `size: XS/S/M/L/XL`. Size measures work, not urgency; split large
   implementations into independently verifiable tasks when appropriate.
4. Read the saved issue's **actual GitHub labels** and reviewed scope again.
   Remove `status: needs triage` only when type, priority, size, duplicate
   disposition and relative queue position have been verified. Keep it while
   a substantive decision remains unresolved.

Human review owns prioritization and triage completion. Never use a CI rule
to auto-score, close or approve ordinary work; the existing live CUBRID,
golden, security and release review criteria remain unchanged.

## Issue Labeling (cubrid-lab org standard)

When creating an issue in this repository, first assign `status: needs triage`.
After review, assign exactly one `priority: <value>` and one `size: <value>`,
alongside a type label (`bug`/`enhancement`/`documentation`/`chore`/`ci`/…) and an
`area:` label when applicable. These must be GitHub labels, not just text in the
issue title or body.

Issue titles use type-only prefixes such as `feat:` or `bug:` (see [organization standard](https://github.com/cubrid-lab/.github/blob/main/docs/ISSUE_PR_COMMIT_STANDARD.md)).

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
2. **Finalize `priority:` and `size:` during maintainer triage.**
   Uncertainty or a provisional label means `status: needs triage` remains.
3. **`good first issue` should be `size: XS` or `size: S`.** If a good-first-issue grows
   past `size: S`, re-scope it or drop the `good first issue` label.
4. **`size: XL` is a signal to split**, not a green light to start a sprawling change.

### Good first issue lifecycle

- **Human-led community contributors, including people directing AI-assisted code:** an unassigned `good first issue` is open for participation. They may start and submit a PR without prior maintainer authorization, GitHub Assignee permissions, or internal agent tooling.
- Before starting, check existing Assignees, comments, and open PRs. An interest comment is welcome but optional; it is neither an approval requirement nor an exclusive reservation. Coordinate before overlapping or taking over claimed work.
- **Maintainer-operated autonomous coding agents:** require explicit maintainer authorization for that specific newcomer-reserved issue and an actual GitHub assignment before implementation. A general request to clear backlog or prepare a release is not authorization.
- Maintainers handle Assignees and labels. Human contributors without assignment rights may still submit PRs; ordinary CI and review gates remain mandatory.
- Unclaimed: retain `good first issue`.
- On opening a PR: maintainers remove `good first issue` and add `status: in progress`, coordinating ownership.
- On merge: close the issue. If a PR closes unmerged: check for other open PRs before restoring `good first issue` and removing `status: in progress`.
- Keep at least three genuinely unclaimed XS/S good first issues with a small blast radius and an existing reference pattern.
- A release-blocker handoff to an autonomous agent needs a recorded maintainer decision after checking Assignees, comments and open PRs.

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
All examples must be independently runnable against CUBRID via Docker (`make docker-up` starts
11.2 by default). The golden-backed examples and most template suites are CI-verified on
CUBRID 11.2 and 11.4; [`SUPPORT_MATRIX.md`](SUPPORT_MATRIX.md) lists each recipe's coverage and
the exceptions (offline-only or not live-covered).

### Key Sections

| Section | Purpose |
|---------|---------|
| `quickstart/` | Get running in 5 minutes |
| `migration/java-to-python/` | Side-by-side Java JDBC → Python migration (killer content) |
| `templates/` | Production-ready application starters |
| `performance/` | Benchmark-backed optimization (linked to cubrid-benchmark data) |
| `pitfalls/` | Common mistakes with CUBRID reserved words, auto-commit, etc. |
| `fundamentals/` | Core DB operations: connect, CRUD, transactions, ORM |

## Human-readable communication (all agents)

Use this rule for text authored or edited by Codex, Claude Code, OpenCode,
ChatGPT, Copilot, or any other agent. It applies to issues, PRs, reviews,
comments, checklists, status updates, commit summaries, release notes,
documentation, presentations, and other maintainer-facing writing.

- Write for a reader unfamiliar with the underlying script, storyboard,
  automation run, or agent plan. Name the actual project, component,
  action, evidence, and location in ordinary, clear language.
- Never use unexplained internal identifiers as reader-facing labels or
  checklist instructions (for example, `H1, P1, C1, K1, F2` or `A1/B1/R1/R2`).
  Do not substitute `P1`/`P2` for repository priority labels.
- When an internal identifier is necessary for accurate cross-reference,
  **describe the subject first**, then add the identifier in context:
  `pycubrid introduction (0:20; storyboard shot P1)`. Use descriptive
  names and timestamps, section titles, or paths wherever practical.
- Use natural, actionable wording. Prefer `Listen to the full narration and
  verify the pronunciation of each project name` to `Maintainer full listen`.
  Avoid compressed task fragments, unexplained acronyms, and generated
  process/status jargon.
- Keep legitimate technical identifiers unchanged in code, tests, structured
  data, logs, specifications, and exact evidence references. Issue numbers,
  filenames, command names, APIs, error codes, and hashes are not prohibited.
  Do not break machine-readable references to improve prose.
- Before publishing, reread the text as a first-time maintainer. It should
  state what happened or needs to happen, why, and where without requiring a
  separate lookup table. Edit an existing editable comment to correct unclear
  wording rather than adding redundant follow-up comments.

Learner-facing recipe comments, sample code, test names, run instructions,
PR descriptions and review replies or summaries follow the organization's
canonical rule,
[Explanations in code, tests, reviews and agent-written text](https://github.com/cubrid-lab/.github/blob/main/docs/ISSUE_PR_COMMIT_STANDARD.md#6-explanations-in-code-tests-reviews-and-agent-written-text).
Explain what a pattern does, why it is safe or useful and the CUBRID or driver
constraint behind it, not which issue introduced it; an issue number may follow
for traceability. Keep comments next to the code they describe, and do not
change test names, golden files, expected output or exact commands to satisfy
this rule. Revise existing comments only where a learner would be confused.

This is a shared writing convention, not a new CI check, reviewer approval,
or merge gate. This repository's recipe, golden/live validation, security and
release rules keep precedence over it.
