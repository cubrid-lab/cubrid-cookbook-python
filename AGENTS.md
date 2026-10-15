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
demos/             → Recording scripts and provenance for the README demo media
docs/              → MkDocs site sources, translations and internal design notes
scripts/           → CI, docs, golden-output and release-verification helpers
tests/             → Offline repository checks (`make test-offline`)
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
an additional GitHub Copilot review is not required. Existing CI,
maintainer/repository checks and live-CUBRID rules still apply.

**Standalone agents (Claude Code, Codex, ChatGPT, or other agent tools):**
implement and test, open a PR, then **wait for a substantive submitted GitHub
Copilot review or a review by a maintainer**, recorded on the PR, before
merging (maintainer decision, 2026-10-15). A maintainer is a code owner in
`.github/CODEOWNERS` other than the PR's author. Reviews by other people, and
reviews by AI agents other than Copilot, are welcome but do not satisfy this
route. A submitted Copilot COMMENTED review with an actual assessment counts as
evidence but is not formal APPROVED status. Requested/pending review, a
boilerplate approval suggestion, self-review or CI success does not qualify.
Validate accepted fixes at the final relevant head; leave the PR unmerged if
the required review has not arrived. No CI check enforces this today; whether
to add one is pending a maintainer decision (#351).

**Security-sensitive paths, under every route:** changes to workflows that hold
write permissions or that sibling repositories call to verify a release
(`smoke-test.yml`), and to the release smoke scripts they run
(`scripts/release_smoke.py`, `scripts/mcp_smoke.py`), get stricter scrutiny.
Their review must explicitly assess what they can write, publish or verify for
other repositories, and a maintainer confirms that disposition before merge.

**`agent-review` check (advisory only):** `.github/workflows/agent-review.yml`
reports from GitHub's own review records whether this route is met (rules in
[CONTRIBUTING.md](CONTRIBUTING.md#agent-review-evidence-gate); the gate is a copy
of cubrid-mcp-server's, with only its constants block changed). It counts a
substantive Copilot review of the head within the two-round budget, or a
maintainer's `APPROVED` review, or `COMMENTED` review that opens an inline
thread; never PR-body checkboxes, pending requests, self-review, other people's
or other AI agents' reviews, summary-only bot text or a review of an older
commit (unless the PR's change against `main` is identical at both commits).
Protected paths (every workflow and composite action, `.github/dependabot.yml`,
`scripts/release_smoke.py`, `scripts/mcp_smoke.py`, the lane selection in
`scripts/ci_scope.py` and `scripts/driver_floors.py`, and the gate itself) need a
maintainer's `APPROVED` review. A PR can publish a check with the same name, so
the check is a reading aid and must not be made a required status check until it
is posted from an identity a PR cannot impersonate (#378). A run triggered by
Copilot's review waits as "action required": re-run it, or edit the PR body,
after Copilot reviews.

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

- Record the development route, the Oracle evidence or the Copilot or
  maintainer review, the reviewer, the relevant reviewed head SHA and
  pending/complete status in the PR.
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

Issues and implementation acceptance are repository-local: file work in the
repository whose code, workflow, or documentation must change. Each repository
owns its scope, priority, assignee, validation, release decision and closure.
Every issue must be understandable without opening another repository's issue.
Cross-repository links are allowed as technical references (Refs owner/repo#N),
but do not transfer work or require another repository to close its issue.
For changes to several repositories, create independent local issues and PRs.
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

- `make check` from the repository root (offline contributor checks)
- `make up` (starts CUBRID 11.2 by default, `CUBRID_VERSION=11.4` to override, with bounded readiness checking)
- `make deps` (installs the drivers, pytest and the golden-backed examples' requirements)
- Run the relevant example: `python <file>.py`
- `make verify VERIFY_PATHS=<example-directory>` for matching live goldens
- `make docs` for staged docs and strict MkDocs validation
- `make docs-check` for links, anchors and recipe commands in every Markdown file (pinned tools: `.github/requirements-docs-check.txt`)
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
All examples must be independently runnable against CUBRID via Docker (`make up` starts
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
