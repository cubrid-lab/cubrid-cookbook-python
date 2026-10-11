# Contributing to cubrid-cookbook-python

Thank you for your interest in contributing! This document provides guidelines
and instructions for contributing to the project.

Use English for GitHub issues, pull requests, and comments; localized documentation
is welcome, and no specific tool is required.

## Table of Contents

- [Development Workflow](#development-workflow)
- [Adding Examples](#adding-examples)
- [Code Style](#code-style)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Pull request and commit titles](#pull-request-and-commit-titles)
- [Reporting Issues](#reporting-issues)

---

## Development Workflow

Every change to an example ships its implementation, tests, and affected docs
**together**; code without affected doc updates is incomplete. Unaffected docs
retain the existing docs-not-needed process.

Maintainer/agent-authored PRs follow the tool-specific route in
[AGENTS.md](AGENTS.md#development-workflow-cubrid-lab-org-standard):
- **OpenCode:** Oracle design review before non-trivial implementation and
  Oracle post-implementation review, with documented findings and validation.
  Trivial OpenCode changes may skip those Oracle phases with a recorded reason.
- **Standalone agents (Claude Code, Codex, ChatGPT, or other agent tools):**
  wait for a substantive submitted GitHub Copilot review or another person's
  review after opening the PR. A pending request, green CI or automated
  approval wording alone does not complete the review route.
- **Human contributions:** normal project review, with no internal agent-tool
  installation requirement. This is not a fallback for unnamed standalone agents.

The applicable review evidence, updated head, dispositions and open threads
must be recorded before merge. Live CUBRID, docs and CI rules remain unchanged.
Maintainers coordinate internal reviews and integration, while contributors
retain authorship and provide ordinary PR evidence.

The existing documentation/coverage rule, not the review-route requirement, is
checked in CI by `scripts/check_docs_sync.py` (the **Docs sync gate** job).
The gate fails when an example directory is missing from README.md,
and warns when an example ships no `expected/` golden file or `tests/` suite.
Run it locally before opening a PR:

```bash
python3 scripts/check_docs_sync.py
```

Intentional coverage exceptions live in `scripts/docs-sync-allowlist.txt` with a
recorded reason.

### Offline contributor checks

From the repository root, install the existing quickstart dependencies and the
small offline test toolchain in a virtual environment:

```bash
python3 -m pip install -r quickstart/5min-fastapi/requirements.txt pytest httpx sqlalchemy ruff==0.16.4
make check
```

`make check` runs Ruff, documentation and golden-coverage checks, output-normalizer
tests, mocked quickstart and AI-agent tests, release dependency guards, and fake
Make/Compose regression tests. `make test-offline` runs just the offline test
suites. Each suite uses its own process to avoid conflicting recipe module names.
These checks require no database and do not prove live CUBRID compatibility;
run the relevant example or `make verify` against CUBRID for that evidence.
CI runs the same `make check` command on every pull request (see
[CI tiers](#ci-tiers) for which live lanes run on top of it).
The repository is an example collection, so `pip install -e .` is not supported.

### CHANGELOG sections

`CHANGELOG.md` `###` headings use the standard list, in this order and only when
they have content: Upgrade notes, Added, Changed, Deprecated, Removed, Fixed,
Security, Performance, Documentation, CI, Tests. Write `Documentation`, not
`Docs`, and put tooling entries under `CI` or `Changed`. `make check-docs` runs
`scripts/lint_changelog.py`, which enforces this for `[Unreleased]` and for releases
after 0.2.0. A fenced `###` line is entry content, never a heading; a fenced `## [` release
header is an error (`scripts/extract_release_notes.py` is not fence-aware and would
truncate the Release body); an unclosed fence is an error. Only fences that start at
column 0 with three backticks are recognised, not tilde or indented/nested fences.

A duplicate `###` heading within one version section is an error only in `[Unreleased]`
and in releases after 0.2.0 (`SECTION_POLICY_CUTOFF`); released history up to 0.2.0 is
never rewritten, and different releases may reuse the same heading names. A duplicate
heading before the first release header is always an error.
`scripts/lint_changelog.py` is identical in pycubrid, sqlalchemy-cubrid,
cubrid-mcp-server and this cookbook except for `SECTION_POLICY_CUTOFF`.

### Dependency updates

`.github/dependabot.yml` keeps dependencies current without flooding the queue:

- **GitHub Actions** — checked weekly; all action bumps arrive as one grouped
  PR. Workflows pin every action by full commit SHA with a `# vX.Y.Z` comment,
  and each action uses the same pin in every workflow;
  `tests/test_dependabot_config.py` (part of `make check`) enforces both.
- **Recipe requirements (pip)** — checked monthly across every standalone
  recipe directory. Updates are grouped by dependency name, so one PR bumps a
  package (for example `flask`) in every recipe that uses it instead of one PR
  per recipe. Major updates of the CUBRID drivers (`pycubrid`,
  `sqlalchemy-cubrid`, `cubrid-mcp-server`) are ignored: their floors are the
  support contract in `SUPPORT_MATRIX.md` and move deliberately.
- Dependabot PR titles use the `chore(deps):` prefix, matching the
  `type(scope): description` title rule.
- `dependabot-auto-merge.yml` enables squash auto-merge for patch and minor
  updates; it completes only after the required checks (`CI Gate` and
  `PR title`) pass. Major updates wait for a maintainer. The `docs-sync` and
  `translation-sync` gates skip Dependabot PRs, since dependency-only bumps
  carry no doc changes.

When a new recipe adds a `requirements.txt` outside the configured
`directories` globs, extend the globs in the same PR; the test above fails
until you do.

### CI tiers

Two workflows share live CUBRID validation (#222). `scripts/ci_scope.py`
classifies each `ci.yml` run from its event and changed paths; a lane starts only
when selected, and the single required `CI Gate (all checks must pass)` accepts a
skipped lane only when the classifier said `false` for it. A failed, cancelled or
unexpectedly skipped lane, or a failed classification, fails the gate.

| Tier | When | What runs |
|------|------|-----------|
| 1 — cheap checks | every pull request | Ruff, `make check`, docs-sync, doc-lint, classification and the gate; the strict docs-site build |
| 2 — path-selected live lanes | pull requests | only the touched family on CUBRID 11.4 / Python 3.12: Flask/FastAPI → the changed recipes' own suites (representative suites for shared files, see below); dashboard, async-worker, Django → their suite; CQRS recipe → its pinned job; golden examples → `Smoke Tests (CUBRID 11.4)` with `make verify` scoped to the touched examples; AI-agent code or other files in example trees → the same lane with a full `make verify` |
| 2 — fan-out | pull requests changing shared live infrastructure (`Makefile`, `docker-compose.yml`, `scripts/normalize_output.sh`, readiness/coverage scripts), `ci.yml`, `scripts/ci_scope.py` or `.github/actions/` | every live lane, both smoke lanes and CQRS on 11.2 + 11.4 with full `make verify`, Python 3.11 + 3.14 compatibility |
| 3 — Python compatibility | push to `main`, weekly schedule, manual `ci.yml` run; pull requests changing `fundamentals/pycubrid`, `fundamentals/sqlalchemy` or fan-out paths | 3.11–3.14 on broad events; 3.11 + 3.14 endpoints on those pull requests |
| 4 — broad smoke | `smoke-test.yml`: push to `main`, nightly schedule, manual run, release verification (`repository_dispatch` / `workflow_call`) | every golden plus all Flask/FastAPI, async-worker, Django and dashboard suites on CUBRID 11.2 + 11.4 (Python 3.12); a release verification adds one CUBRID 11.4 cell on Python 3.11, the supported minimum |

- Docs-only pull requests (`*.md`, `docs/`, `mkdocs.yml`, …) start no live CUBRID,
  except `SUPPORT_MATRIX.md`, which documents the driver floors.
- `Driver floors (CUBRID 11.4)` (#241) installs every documented driver floor
  exactly (`scripts/driver_floors.py`, one virtual environment per floor set,
  Python 3.12) and diffs representative goldens against live CUBRID 11.4. It runs
  on pull requests that change `SUPPORT_MATRIX.md`, the floor checker or lane, or
  the `requirements.txt` of a directory the lane runs (`ci_scope.FLOORS`), on the
  weekly `ci.yml` schedule and on manual `ci.yml` runs — not on pushes to `main`,
  since the floors are fixed releases; edits to a lane directory's code do not select it, the weekly schedule covers them. One job, about 3 minutes.
  Unknown paths fail closed to every recipe family lane and the 11.4 smoke lane
  with a full `make verify`.
- CUBRID 11.2 runs on a pull request only for version-sensitive changes:
  `smoke-test.yml`, `scripts/release_smoke.py`, `scripts/mcp_smoke.py`, the
  fan-out paths, or recipe 10's `requirements.txt` (CQRS job only).
- Example directories with no live consumer (`performance/`, the FastAPI
  quickstart, `fundamentals/parameterized-queries`) are covered by the offline
  checks only, on every event.
- The Flask/FastAPI lane (#227) runs the `tests/` suite of each changed recipe
  root (`ci_scope.web_suites`: a `templates/flask/` or
  `templates/api-service-fastapi/recipes/` recipe, or the root FastAPI app), each
  in a fresh venv with only its own `requirements.txt` and its own pytest
  process, against one CUBRID 11.4 container. Shared Flask/FastAPI files (for
  example `templates/flask/requirements.txt`), fan-out paths and unknown paths
  add the representative suites (`templates/flask/01-basic-crud`,
  `templates/api-service-fastapi/recipes/01-basic-crud`, the root FastAPI app).
  The representatives run on top of the changed recipes and never count toward
  the cap: at most `MAX_WEB_SUITES` (25) changed recipe roots run per pull
  request. A suite takes about 11 s, so the cap covers every suite in the
  repository (23 today; `tests/test_ci_scope.py` fails when a new recipe
  outgrows it), and a grouped Dependabot bump runs every suite it touches.
  Should changed roots ever exceed the cap, the first 25 by name and the
  representatives run, and the rest (`ci_scope.web_suites_skipped`) get a
  `::warning::` each and a "Not validated before merge" list in the job
  summary, so a green gate is never presented as their coverage; for live
  evidence before merging, run
  `gh workflow run smoke-test.yml -R cubrid-lab/cubrid-cookbook-python --ref <branch>`,
  otherwise `smoke-test.yml` covers them after merge.
  `dependabot-auto-merge.yml` does not read this list: with the cap above the
  suite count it cannot be non-empty on a real pull request. Recipe 10 runs
  only in its CQRS job. Every selected suite must pass at least one test
  (checked on pytest's final summary line) within 10 minutes, or the lane and
  `CI Gate` fail.
- `smoke-test.yml` does not run on pull requests, so no pull request repeats the
  broad 11.2/11.4 matrix. Its exact release verification inputs, outputs and
  fail-closed reporting are unchanged. To test a change to it before merging, run
  `gh workflow run smoke-test.yml -R cubrid-lab/cubrid-cookbook-python --ref <branch>`.
- The check names `Smoke Tests (CUBRID 11.2)` and `Smoke Tests (CUBRID 11.4)`
  now come from the two `ci.yml` pull-request smoke lanes
  (`.github/actions/pr-smoke`). When the classifier skips a lane its check
  reports *skipped*. `CI Gate` enforces every selected lane, including these
  two, so the lanes are not separate required checks (see
  [Main branch protection](#main-branch-protection)).
- On `main` and schedule events `ci.yml` runs only what `smoke-test.yml` does not
  cover (Python 3.11–3.14 and CQRS pins on 11.2 + 11.4); its other live jobs
  report skipped there.
- Dependabot grouping is unchanged. A grouped multi-directory recipe bump starts
  only the families it touches (for example a Flask bump: one Flask/FastAPI lane)
  plus the cheap checks; a GitHub Actions group bump edits `ci.yml` and therefore
  fans out.
- The nightly `smoke-test.yml` schedule stays daily: between 2026-09-01 and
  2026-10-07, 10 of 37 scheduled runs failed in `make verify`, most on days
  without a `main` push (2026-09-03 to 09-08, 09-25/26), so main pushes alone
  would have detected those regressions days later.
- **Advisory driver-main lane (#239), never gated.** `.github/workflows/driver-main.yml`
  installs `pycubrid` and `sqlalchemy-cubrid` from their `main` branches (pinned
  to the commits resolved at the start of the run, and verified after install)
  and runs `make verify` on representative golden directories against CUBRID
  11.4. It has no schedule of its own: the weekly `ci.yml` schedule calls it
  (job `driver-main-advisory`, outside `CI Gate`), and it can be dispatched with
  `gh workflow run driver-main.yml -R cubrid-lab/cubrid-cookbook-python`. A
  scheduled call is skipped when neither driver's `main` has a commit from the
  last 8 days, and the lane runs only in the upstream repository. Its recipe job
  has `continue-on-error`, so a break leaves the run green; the run summary and
  one tracking issue ("ci: cookbook recipes failing against driver main",
  opened, commented on and closed automatically) carry the signal. The issue is
  closed only by the next run that actually executes the recipes; when both
  drivers are idle for 8 or more days, close it with a manual dispatch on `main`
  once the recipes pass (a dispatch from another branch never touches it). No pull
  request runs it, and it cannot block a merge.

Measured before/after (#222; "before" = median of real runs since 2026-10-03 with
the current job set; "after" = the classifier applied to the files of the last 40
merged pull requests, using the same per-job median durations; billed minutes
round each job up to a whole minute):

| Event | Before jobs (live) | Before job-min / billed | After jobs (live) | After job-min / billed |
|-------|-------------------|-------------------------|-------------------|------------------------|
| Docs-only PR | 21 (12) | 13.3 / 24 | 10 (0) | 1.6 / 10 |
| Dependabot pip recipe bump | 21 (12) | 13.3 / 24 | 11 (2) | 2.9 / 11 |
| Path-selected PR (median of `pr` tier) | 21 (12) | 13.3 / 24 | 11.5 (2) | 4.3 / 13 |
| CI or shared-infrastructure PR | 21 (12) | 13.3 / 24 | 20 (10) | 13.7 / 26 |
| Last 40 merged PRs, total | 840 (480) | 532 / 960 | 598 (204) | 323 / 734 |
| Push to `main` (`ci.yml` + `smoke-test.yml`) | 21 (12) | 16.3 / 28 | 17 (8) | 11.9 / 22 |
| Schedule | 2 (2) daily | 6.1 / 7 per day | unchanged daily, plus `ci.yml` weekly 15 (6) | + ~5.7 / 15 per week |

---

### Job timeouts

Every executing job sets an integer `timeout-minutes` instead of GitHub's
360-minute default (#228): 2–5 minutes for gates and small jobs, 10 for lint and
the docs build, 15 for the offline checks and the docs deploy, 30 for the PR smoke
lanes, and 60 for `smoke-test.yml`'s `verify` job, whose step-level timeouts add up
to 57 (plus a few untimed setup steps; the observed maximum is 4 minutes).
Jobs that call the organization's reusable workflows (`doc-lint`, `live-smoke`)
cannot set a timeout; those callees are an exact allowlist.
`tests/test_workflow_timeouts.py` (run by `make check`) reads every workflow and
fails when an executing job lacks a bounded timeout, when a new external caller is
not allowlisted, or when `CI Gate` loses `if: always()` or its short timeout.

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
make up

# Example: run a FastAPI template
cd templates/api-service-fastapi/recipes/01-basic-crud
pip install -r requirements.txt
uvicorn main:app --reload

# After stopping Uvicorn, return to the repository root for a fundamental
cd ../../../..
python fundamentals/pycubrid/01_connect.py
```

`make up` starts Compose, then waits up to 120 seconds for the existing
in-container `csql` query to succeed. Each probe and failure diagnostic has a
5-second limit. To adjust these waits, use `UP_TIMEOUT`, `UP_PROBE_TIMEOUT`, and
`UP_INTERVAL`, for example `make up UP_TIMEOUT=180`. Image pull/start time occurs
before the readiness deadline. This query checks the database inside the
container; it does not verify the driver's CAS connection. On failure the
command exits nonzero and prints bounded Compose status/log diagnostics, leaving
the containers and data available for inspection.

The root Compose image defaults to CUBRID 11.2. Select another version without
editing the file: `make down`, then `CUBRID_VERSION=11.4 make up` (combine with
`UP_TIMEOUT=180` if needed). These commands retain the existing volume; changing
the server image is not a database-format upgrade. Use fresh, isolated test data
when switching incompatible versions, and never delete existing data implicitly.

### Golden Verification

Runnable examples are checked against committed golden output with `make verify`,
which discovers each committed `<dir>/expected/<name>.expected`, runs the matching
`<dir>/<name>.py`, pipes it through `scripts/normalize_output.sh`, and diffs the
result against that golden file. When you add a one-shot example, capture its
golden output so CI can guard it.

`make verify` checks all goldens by default; use `VERIFY_PATHS=<directory>` to
select example roots. Empty/missing roots, zero golden targets, a missing script
for an expected file, discovery/read errors, and failed scripts or normalizers
all fail the command. A successful summary has at least one pass and no failures
or skips. Ordinary recipe failures are collected so the remaining selected
recipes still produce diagnostics.

To reproduce it from a clean checkout, use a Python 3.11+ virtual environment and
run `make up`, `make deps`, `make verify`. `make deps` installs `pytest`,
`sqlalchemy-cubrid[pycubrid]` and the `requirements.txt` of every golden-backed
example (a directory that owns `expected/`) in one pip resolver call, so
`PIP_CONSTRAINT` applies to all of them. The same discovery
(`scripts/example_requirements.py`) backs `scripts/release_smoke.py
install-examples` in CI; it fails, and so does `make deps`, if a
golden-backed `requirements.txt` path contains whitespace. Before running anything, `make verify` checks that the
selected examples' requirements are installed and stops once with "run
`make deps` first" if not.

Each script runs through `scripts/run_example.py` with a `VERIFY_TIMEOUT`
wall-clock limit (default 60 seconds; the slowest golden took about 7 seconds on
CUBRID 11.4) and stdin redirected from `/dev/null`. The script runs in its own
process group, and the whole group (including helpers it started) is killed on
timeout, when the script exits, and when the runner gets SIGINT, SIGTERM or
SIGHUP (it then exits 128 + the signal number). The runner is POSIX-only and
exits with "run_example.py requires POSIX process groups" elsewhere. Every
result is classified as `✓ PASS`, `✗ MISMATCH` (with a diff), `✗ EXEC-ERROR`
(exit status and the last 20 output lines; a script killed by a signal N reports
128 + N), `⏱ TIMEOUT` (the last 20 lines; only when exit 124 comes with the
runner's `run_example: timed out after` line, so a script that itself exits 124
is an `EXEC-ERROR`),
`✗ NORMALIZE-ERROR`, `✗ READ-ERROR` (golden read error) or `? SKIP`, and the
summary counts each class. Under GitHub Actions each failure also emits an
`::error file=...::` annotation.

This is enforced: `scripts/check_expected_coverage.py` (run by `make verify` and
the smoke-test workflow) fails if any runnable `<dir>/*.py` inside a directory
that owns an `expected/` folder has no matching `expected/<name>.expected`
golden. To opt a script out, add it to `scripts/verify_exclusions.txt` with a
reason — but prefer making the example deterministic and adding a golden.

#### Dependency floors

Every standalone example/template `requirements.txt` is installed on its own
(`pip install -r requirements.txt` in that directory, per its README), so an
unversioned `pycubrid`/`sqlalchemy-cubrid` line can silently resolve to a
release far below anything this cookbook runs against. `SUPPORT_MATRIX.md`'s
"Driver & Framework Versions" table is the single documented floor
(`pycubrid>=1.6.1`, `sqlalchemy-cubrid>=1.0`); recipes that need more pin a
higher floor only when SUPPORT_MATRIX.md explains why (the `[^async]`
footnote's "advanced" SQLAlchemy recipes at `>=1.4.2` and `fundamentals/async` at `>=1.5`;
`fundamentals/orm-basics` and the full example apps under `templates/` at the
`>=1.7,<2` line the drivers are actually published as; `fundamentals/pycubrid`
at `>=1.9,<2` for errno-carrying batch errors, the CAS-session fix and typed collection binding;
`fundamentals/sqlalchemy` at `pycubrid>=1.9,<2` and `sqlalchemy-cubrid>=1.9` for typed collection binding).
`scripts/check_dependency_floors.py` (run by `make check`) fails on a bare
driver requirement, a floor below its applicable minimum, or an undocumented
custom floor — add it as a named exception in both the script and
SUPPORT_MATRIX.md instead of pinning it ad hoc. The checker accepts extras
(`sqlalchemy-cubrid[pycubrid]>=1.0`) and spaces around the specifier. Floors are
also installed and run: the `Driver floors (CUBRID 11.4)` CI lane
(`scripts/driver_floors.py`, see [CI tiers](#ci-tiers)) installs each floor with
`==` and runs representative goldens; a new directory-specific floor must be
added to a floor set there, or `tests/test_dependency_floors.py` fails. Run it
locally against `make up` with `python scripts/driver_floors.py run`.

#### Release smoke dependencies

The smoke job selects `pycubrid` and `sqlalchemy-cubrid` from the package index,
then freezes their exact installed versions with `scripts/release_smoke.py`.
Every subsequent dependency install uses these constraints, including example
requirements, AI-agent and framework test dependencies, and the MCP server. An incompatible
requirement fails the job instead of replacing a selected driver.

After all installs, the job checks the driver versions and package-index origin
before recording **Tested upstream versions** and running examples or suites.
The AI-agent suite runs twice only after this final verification, on PRs too.
A same-version VCS or local install is also rejected. Golden-backed requirements
must use published driver releases; the `pycubrid`, `connect`, and `orm-basics`
fundamentals require the current `>=1.7,<2` release line.

Release dispatches accept `pycubrid`, `sqlalchemy-cubrid`, or `cubrid-mcp-server`
with a canonical `vMAJOR.MINOR.PATCH` ref, matching the upstream dispatch format.
The job reads the event JSON, validates the request before installation, and
installs that exact release from PyPI. Before installing, it polls the PyPI JSON
API (`https://pypi.org/pypi/<package>/<version>/json`, anonymous, no token) until
that exact version is listed with at least one wheel or sdist, backing off
5, 10, 20, then 30 seconds between polls within a 600-second wall-clock budget.
HTTP errors, malformed JSON, another version or a release without files all
count as "not served yet"; when the budget runs out the job fails with
`PyPI does not serve <package>==<version> after N s (<last reason>)`, naming
the last error or what PyPI served instead (version and wheel/sdist count),
and never falls back to another version. This absorbs stale PyPI CDN nodes, which on 2026-10-09 hid a
fresh driver upload from one smoke cell for about 95–106 seconds while the other
cell already installed it. Because the JSON API and the simple index can still
briefly disagree, the install itself (`pip install --no-cache-dir`) is then
retried up to six times, with a 60-second installer timeout and 10 seconds
between attempts (at most 410 seconds). The *Select released drivers* step allows
20 minutes for both budgets. Runs without a requested release never poll PyPI.
The requested package is pinned through later installs and checked again for its
exact version and package-index origin before tests.

The intentional MCP git-tag fallback applies only when MCP is not the requested
package. Its actual origin remains visible in the result summary. Requested
releases always use the exact PyPI artifact. The final summary runs on failures
too and includes the request, installed versions/origins, verification commit,
actual CUBRID server version when available, and job result. This handles the
tag/publication race in the receiver; upstream notification timing is unchanged.

When the upstream dispatch token is unavailable, maintainers verify a release by
running the workflow manually with the same package allowlist and an exact version
(`MAJOR.MINOR.PATCH` or `vMAJOR.MINOR.PATCH`):

```bash
gh workflow run smoke-test.yml -R cubrid-lab/cubrid-cookbook-python \
  -f package=pycubrid -f version=1.8.0
```

These inputs are read from the event JSON and follow the same validation, exact
PyPI install, bounded retry, pinning, origin check and summary as a release
dispatch; an invalid, unavailable or mismatched release fails instead of testing
the latest release. A manual run with the default inputs (`package=latest`, empty
`version`), like pushes and the nightly schedule, is an ordinary
smoke run on the latest published releases and is reported as not a release
verification.

##### Release verification contract (for upstream release workflows)

The automated releases in `pycubrid`, `sqlalchemy-cubrid` and `cubrid-mcp-server`
verify the cookbook either by **calling `smoke-test.yml` as a reusable workflow**
(preferred: no token, see [Calling the smoke test from a release workflow](#calling-the-smoke-test-from-a-release-workflow-no-token))
or by dispatching a verification and then waiting for **that** run. This repository
commits to the following interface; changing it is a breaking change for those
workflows.

**Request.** Either a `repository_dispatch` with `event_type: upstream-released`:

```json
{"event_type": "upstream-released",
 "client_payload": {"package": "pycubrid", "ref": "v1.8.0", "request_id": "pycubrid-v1.8.0-123456789-1"}}
```

or a manual run: `gh workflow run smoke-test.yml -R cubrid-lab/cubrid-cookbook-python
-f package=pycubrid -f version=1.8.0 -f request_id=<id>`.

| Field | Rule |
| --- | --- |
| `package` | `pycubrid`, `sqlalchemy-cubrid` or `cubrid-mcp-server` |
| `ref` (dispatch) | canonical `vMAJOR.MINOR.PATCH` |
| `version` (manual) | `MAJOR.MINOR.PATCH` or `vMAJOR.MINOR.PATCH` |
| `request_id` | optional, `^[A-Za-z0-9._-]{8,80}$`; required in practice to find the run |

All fields are read and validated from the event JSON by `scripts/release_smoke.py`
(from the call inputs for a workflow call); an invalid `request_id` fails the run
before any install. A manual `request_id`
without a pinned package is rejected.

**Finding the run.** A release verification run is named

```text
Release verification <package>@<ref or version as sent> [request_id=<request_id>]
```

(`[request_id=none]` when absent). Poll
`GET /repos/cubrid-lab/cubrid-cookbook-python/actions/workflows/smoke-test.yml/runs?event=repository_dispatch`
(or `event=workflow_dispatch`, optionally `created=>=<dispatch time>`) and select the
run whose `display_title` contains the exact token `[request_id=<request_id>]`. Other
runs (pushes, pull requests, the schedule, manual `latest` runs) keep the default name.
Each request gets its own non-cancelling concurrency group (event, package, version,
request id and run), so two verifications never replace each other and a called run
never shares the caller's group.

**Result.** The run's `conclusion` is `success` only when every smoke job passes (CUBRID 11.2 and
11.4 on Python 3.12, plus CUBRID 11.4 on Python 3.11) and every job installed exactly the requested version from PyPI. The
`Release verification report` job then publishes, for every release request:

- a job summary table (`request_id`, `package`, `requested_version`,
  `installed_version`, `status`, plus the failure reasons);
- step outputs `release`, `artifact`, `status`, `request_id`, `package`,
  `requested_version`, `installed_version`;
- an artifact named `release-verification-<request_id>` (or
  `release-verification-run-<run_id>` without a valid request id), retained 30 days
  and replaced when failed jobs are re-run in the same run,
  containing `release-verification.json`:

```json
{
  "schema_version": 1,
  "request_id": "pycubrid-v1.8.0-123456789-1",
  "package": "pycubrid",
  "requested_version": "1.8.0",
  "installed_version": "1.8.0",
  "status": "success",
  "reasons": [],
  "run": {"id": "…", "attempt": "1", "url": "https://github.com/…/actions/runs/…",
          "commit": "<cookbook SHA>", "event": "repository_dispatch"},
  "matrix": [
    {"cubrid": "11.2", "python": "3.12", "request_valid": true, "installed_version": "1.8.0",
     "origin": "package index", "server": "11.2.x", "verification": "passed",
     "result": "success"},
    {"cubrid": "11.4", "python": "3.12", "…": "…"},
    {"cubrid": "11.4", "python": "3.11", "…": "…"}
  ]
}
```

`status` is `success` or `failure`; `installed_version` is `null` unless every job
installed the same version, and a failure lists its `reasons` (invalid request,
missing or failed jobs, a smoke result download that did not succeed,
`installed X differs from requested Y`). The report job
itself fails whenever `status` is `failure`. An upstream verifier should require the
run conclusion `success` **and** the artifact's `status == "success"` with
`installed_version == requested_version`. Publication delay is absorbed inside the
run by the bounded retry above; a release that never appears fails, and the run never
falls back to the latest release or to `main`.

##### Calling the smoke test from a release workflow (no token)

This repository is public, so a release workflow can run the whole smoke test as a
job of its **own** run with its own `GITHUB_TOKEN` — no PAT, no
`COOKBOOK_DISPATCH_TOKEN`, no secrets and no polling:

```yaml
  cookbook-smoke:
    needs: publish                     # after the release is on PyPI
    permissions:
      contents: read                   # all the called workflow needs
    uses: cubrid-lab/cubrid-cookbook-python/.github/workflows/smoke-test.yml@<40-hex cookbook commit> # main
    with:
      package: pycubrid                # pycubrid | sqlalchemy-cubrid | cubrid-mcp-server
      version: ${{ needs.publish.outputs.version }}   # X.Y.Z or vX.Y.Z
      request_id: pycubrid-v${{ needs.publish.outputs.version }}-${{ github.run_id }}-${{ github.run_attempt }}

  require-cookbook:
    needs: cookbook-smoke
    if: ${{ always() }}
    runs-on: ubuntu-latest
    steps:
      - env:
          STATUS: ${{ needs.cookbook-smoke.outputs.status }}
          REQUESTED: ${{ needs.cookbook-smoke.outputs.requested_version }}
          INSTALLED: ${{ needs.cookbook-smoke.outputs.installed_version }}
        run: |
          [ "$STATUS" = success ] && [ -n "$INSTALLED" ] && [ "$INSTALLED" = "$REQUESTED" ]
```

| Input | Rule |
| --- | --- |
| `package` | required; `pycubrid`, `sqlalchemy-cubrid` or `cubrid-mcp-server` |
| `version` | required; `MAJOR.MINOR.PATCH` or `vMAJOR.MINOR.PATCH` |
| `request_id` | optional, `^[A-Za-z0-9._-]{8,80}$`; names the report artifact |

| Output | Value |
| --- | --- |
| `status` | `success` or `failure` (see **Result** above) |
| `requested_version` | normalized `MAJOR.MINOR.PATCH` |
| `installed_version` | the version every smoke job installed, empty unless they agree |
| `artifact` | report artifact name in the caller's run (`release-verification-<request_id>`) |

The called run behaves exactly like a release dispatch: the exact PyPI install after
the bounded PyPI publication wait and install retry, no fallback to the latest release or to `main`, both
CUBRID jobs, the same report job and `release-verification.json` schema (with
`run.event` = `workflow_call` and `run.commit` = the cookbook commit tested). The
caller job fails when the verification fails; the outputs are still set, so a
following job with `if: always()` can report them.

- **Pin a full commit SHA** of this repository (a `main` commit), like any
  third-party action. Every job checks out **this** repository at exactly that
  commit (`job.workflow_sha`), never the caller's repository or `main`.
- Under `workflow_call` GitHub gives the called jobs the caller's `github` context
  and event (for example the release `push`), so `smoke-test.yml` detects the call
  by comparing `job.workflow_ref` with `github.workflow_ref` and passes the call
  inputs to `scripts/release_smoke.py` as `RELEASE_INPUT_*` environment variables,
  never as shell code; the caller's event JSON is ignored.
- The calling job must grant at least `contents: read`. Nothing else is needed:
  artifacts are uploaded to and downloaded from the caller's run with the runner's
  own artifact token. The call inherits no secrets.
- The jobs appear in the caller's run as `<calling job> / Smoke Tests (CUBRID 11.2)`,
  `… (CUBRID 11.4)`, `… (CUBRID 11.4, Python 3.11)` and
  `… / Release verification report`, and upload the artifacts
  `release-verification-part-cubrid-11.2`, `release-verification-part-cubrid-11.4`,
  `release-verification-part-cubrid-11.4-py3.11` and `release-verification-<request_id>`. Call the workflow at most once per
  caller run in this mode.

A pre-publish **candidate mode** verifies the caller's own built wheel before
`publish` (#240). It is selected only with `mode: candidate` plus `candidate_artifact`,
`candidate_hashes` and `candidate_source_sha`, and requires a `request_id` that stays
the same across run attempts (use `github.run_id`, never `github.run_attempt`, and no
`--`), so `gh run rerun --failed` replaces only the failed cells' parts. The defaults keep the published
mode described above unchanged. In candidate mode the workflow verifies the
artifact's file set, SHA-256 digests and wheel metadata before installing, and
keeps that wheel installed through every later install. It adds the outputs
`evidence` and `candidate_sha256` and uses its own `release-candidate-*` artifact
names, so a caller may call it once per mode in one run. The full inputs, outputs,
report fields, failure modes and caller shape are in
[docs/internal/rc-verification-design.md, section 13](docs/internal/rc-verification-design.md#13-implemented-cookbook-contract-c1-c2).

Run the smoke dependency guards without a database or network:

```bash
python3 -m unittest discover -s tests -p 'test_release*.py' -v
```

#### Excluded from golden verification

Some examples are **intentionally** outside `make verify`. They are still real,
runnable examples — they just can't be captured as a deterministic one-shot
golden. If you see one of these without an `expected/` file, that is expected
and not missing coverage:

| Example | Why it is excluded |
|---------|--------------------|
| `quickstart/5min-fastapi` | Long-lived ASGI web service (`uvicorn`) exercised via HTTP, not a deterministic one-shot script — it runs until stopped, so there is no single terminal output to golden-capture. |
| `templates/django` | Long-lived Django HTTP service; its documented SQLAlchemy/CUBRID bridge is exercised by `templates/django/tests` against live CUBRID, not by a one-shot stdout golden. |
| `templates/async-worker` | The long-lived Celery worker requires an external broker (Redis), so it has no one-shot golden. Its CUBRID database tasks are tested separately by `templates/async-worker/tests` without a broker. |
| `performance/bulk-insert/benchmark.py` | Throughput benchmark — prints wall-clock timings and rows/sec that vary run-to-run. |
| `performance/connection-pooling/benchmark.py` | Throughput benchmark — timings and speedup factors are nondeterministic. |
| `performance/fetch-optimization/benchmark.py` | Throughput benchmark — per-strategy timings are nondeterministic. |

Where output is dynamic only in *presentation* (timings, absolute paths, peak
memory), prefer adding a presentation-only rule to `scripts/normalize_output.sh`
(see `make test-normalize`) so the example can be golden-captured instead of
excluded. Reserve exclusion for examples that never produce deterministic,
one-shot terminal output.

### Documentation site

The [documentation site](https://cubrid-lab.github.io/cubrid-cookbook-python/)
is built from the repository docs; the repository files stay the source of truth.

- `scripts/stage_docs.sh` (implemented in `scripts/stage_docs.py`) copies the
  root and topic READMEs listed there into `docs/` (the copies are gitignored)
  and rewrites their relative links: links to another staged page point at
  that page, and links to any other repository path (recipe directories,
  `.py` files, `LICENSE`, `docs/internal/`) become GitHub URLs on `main`.
  Keep writing ordinary repository-relative links in the sources; a link to a
  path that does not exist fails staging.
- `mkdocs.yml` turns unresolved, unrecognized and broken-anchor links into
  warnings, so `make docs` (`mkdocs build --strict`) fails on them. CI runs
  `make docs` on every PR (`Docs site build (strict)`).
- `docs/internal/` (planning material such as the PRD) is excluded from the
  rendered site and its search index.
- `docs/quickstart.md` is a hand-maintained site guide condensed from
  `GETTING_STARTED.md`, which remains the source of truth. When a change to
  `GETTING_STARTED.md` affects its commands or steps, update
  `docs/quickstart.md` in the same PR.

---

## Code Style

### Python

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

- **Line length**: 100 characters
- **Target Python**: 3.11+
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
- Title the PR as described in
  [Pull request and commit titles](#pull-request-and-commit-titles), and write a
  description explaining _what_ and _why_.
- Reference any related issues in the PR body (e.g., `Fixes #42`), not in the title.
- Record commands actually executed, their results, and any checks not run with
  the reason. Optional AI/tool review is separate evidence and does not replace
  lint, tests, documentation checks, or live compatibility validation.

Behavior, SQL, installation, and compatibility changes need matching source docs
in the same PR. If docs are genuinely unaffected, add a standalone, unfenced line
such as `Docs: not needed - only regression test data changed` to the PR body.
Use a standalone physical source line outside quoted/commented/code examples.
A blank line or quoted blank line can end a preceding Markdown quote; ordinary
prose before or after the reason does not require a blank paragraph separator.
The docs gate rejects blank reasons, the literal `<reason>` placeholder, and
markers shown only in quotes, comments, or fenced examples. The explanation
must contain visible text: empty emphasized link captions such as
`[**<!-- empty -->**](/issue)` or `[**![](/img)**](/issue)` do not supply a reason,
while `[**tests only**](/issue)` does. The existing
`docs-not-needed` label remains a maintainer-managed exception for this gate.

If you need translation help, name the missing language and reason in the PR.
This request does not bypass checks: Korean README synchronization remains
required, while other community translation drift is advisory. Only explicit
maintainer approval via the existing `translations-deferred` label skips that
gate; maintainers record and own the follow-up.

The shared documentation-lint and live-smoke callers use reviewed commit SHAs.
Maintainers update them through a PR after verifying the upstream commit,
workflow files and inputs, while retaining caller inputs, permissions and gates.
The documentation scanner and configuration still download from upstream main;
pinning the caller alone does not freeze those resources.

### Review Process

- All PRs must complete the applicable AGENTS.md development-tool review route
  before merge. Non-trivial OpenCode work records Oracle pre/post evidence;
  trivial OpenCode edits may omit those reviews with a recorded reason.
  Standalone Claude Code, Codex, ChatGPT and other agent tools require a
  substantive submitted GitHub Copilot review or another person's review.
  A pending request does not complete the route. Human contributions follow
  ordinary review, and outstanding review threads need a disposition.
- CI must pass (lint checks).
- Examples must be tested against a live CUBRID instance.

Explain unavailable local checks so maintainers can arrange validation. A reason
or an AI review does not waive the CI or live checks required before merge.
Outside contributors do not need internal AI tools, label permissions or live
CUBRID access; when a required integration check is missing, maintainers own
running it.

### Code ownership

`.github/CODEOWNERS` routes review requests for a small set of high-blast-radius
surfaces to the maintainers: `.github/workflows/` (including the reusable
`smoke-test.yml` release verification contract) and the composite actions in
`.github/actions/`, `.github/dependabot.yml`, `.github/CODEOWNERS`, `SECURITY.md`,
and the shared validation and golden-output infrastructure (`Makefile`,
`scripts/`, the shared tests in `tests/`, `docker-compose.yml`, `pyproject.toml`).
Individual recipes, and recipe-specific tests such as `tests/test_ai_agent*.py`,
are intentionally not owned, so ordinary recipe contributions need no special
reviewer. CODEOWNERS is routing only, not a security boundary, and does not by
itself make any approval mandatory.

### Main branch protection

Every change reaches `main` through a pull request. The maintainers apply this
baseline to `main` (the default branch) as a repository ruleset in the
repository settings. It is not stored in the repository, so a change to it is a
maintainer decision recorded on an issue, not a pull request:

- **No deletion** of `main`.
- **No force push** (non-fast-forward updates are rejected).
- **Pull request required.** Direct pushes to `main` are rejected. Merges are
  squash merges, so the pull request title becomes the commit title.
- **Required checks:** `CI Gate (all checks must pass)` (the aggregate gate
  described in [CI tiers](#ci-tiers)) and `PR title` (from `pr-title.yml`). The
  branch must be up to date with `main` before merging. The gate already fails
  when a selected lane fails, is cancelled or is skipped unexpectedly, so the
  individual lanes, including `Smoke Tests (CUBRID 11.2)` and
  `Smoke Tests (CUBRID 11.4)`, are not required checks themselves. A lane that
  the classifier did not select never blocks a merge.
- **No required human approval and no required code-owner approval.** The
  project has a small maintainer team. A mandatory approval would block a
  maintainer's own pull request whenever the other maintainers are away, and
  Dependabot updates would wait for a human approval instead of merging
  automatically once the required checks pass. The review route in
  [Review Process](#review-process) still applies before a maintainer merges,
  and `.github/CODEOWNERS` only routes review requests.
- **No bypass actor.** The rules also apply to administrators. No workflow
  pushes to `main`: `docs.yml` deploys the documentation site from a Pages
  artifact, `dependabot-auto-merge.yml` merges through the pull request with the
  same required checks, and this repository has no release automation.

The ruleset does not affect release verification. Sibling release workflows
call `smoke-test.yml` pinned to a full commit SHA (see
[Calling the smoke test from a release workflow](#calling-the-smoke-test-from-a-release-workflow-no-token)),
and the called jobs run in the caller's repository. Rules on this repository's
`main` govern pushes and merges to it, not reading a workflow at a commit, and
they do not restrict `repository_dispatch` either.

Changing the display name of the `ci-gate` job (`CI Gate (all checks must
pass)`) or of the `pr-title` job (`PR title`) changes the check name and blocks
every merge until the required checks are updated in the ruleset; change both
together.

---

## Repository-local issue ownership

Issues own implementation and acceptance in the repository whose files change.
Provide a self-contained local problem, scope, owner, tests, and closure decision.
Sibling repositories may be cited with Refs owner/repo#N when they supply a real
dependency or compatibility contract; their priorities and completion are not
inherited. Close only this repository's issues (Closes #N). PRs with no local
issue may state N/A and a reason. The existing PR title check rejects direct
cross-repository issue-closing keywords in the PR body; commit messages are not
checked, so keep foreign closing keywords out of them too. External contributors
do not need to install internal agent tools or create duplicate work.

## Pull request and commit titles

This rule covers issue titles, pull request titles and commit subjects in every
cubrid-lab repository. Pull requests are squash-merged and the pull request
title becomes the commit title on `main`, so the pull request title is the one
that must be right. The `PR title` check enforces it.

```text
type: description
type(scope): description
type!: description
type(scope)!: description
```

- **type** (lowercase, exactly one of): `feat`, `fix`, `docs`, `test`, `perf`,
  `refactor`, `ci`, `build`, `chore`, `style`, `revert`.
- **scope** is optional: lowercase letters, digits, `-` or `_`, such as
  `compiler`, `aio`, `deps` or `release`.
- **`!`** before the colon marks a breaking change. Follow the repository's
  release policy for breaking changes as well.
- Exactly **one space** after the colon.
- **description**: English and specific (name the function, type or behavior
  that changed). Start with a lowercase letter unless the first word is an API
  name, acronym or proper noun. No trailing period.
- No bracket, status or priority prefixes (`[Bug]`, `[WIP]`, `Track:`,
  `epic:`, `P1`). Open a draft pull request for unfinished work; priority and
  size are labels.
- No issue or pull request numbers in the title. Put `Closes #123` or
  `Refs #123` in the pull request body. GitHub appends the pull request
  number, for example `(#456)`, to the squash commit by itself.

| Type | Use for |
|------|---------|
| `feat` | A new user-facing capability |
| `fix` | Corrects wrong behavior, including security fixes |
| `docs` | Documentation only |
| `test` | Tests only |
| `perf` | Faster or lighter with no behavior change |
| `refactor` | Restructuring with no behavior change |
| `ci` | CI workflows and their configuration |
| `build` | Packaging and the build system |
| `chore` | Maintenance: releases, dependency bumps, housekeeping |
| `style` | Formatting only |
| `revert` | Reverts an earlier change; name it in the description |

Examples:

```text
fix(protocol): keep the CAS session after OUT_TRAN
feat(aio): add a charset connection option
docs: document JSON as_numeric() input limits
chore(deps): bump ruff from 0.16.8 to 0.16.9
chore: release v1.9.0
refactor(compiler)!: drop legacy LIMIT rendering
```

Issue forms prefill a type prefix; keep it and write the rest of the title the
same way. A tracking issue (epic) uses the type of the work it tracks.

Maintainers merge with **squash merge only** and keep the pull request title as
the commit title. Branch commits are squashed into the commit body, so keep
their messages meaningful and keep any `Co-authored-by:` trailers intact.

---

## Reporting Issues

When reporting a bug in an example, please include:

- Which example you're running
- Python version
- CUBRID server version
- Full error output
- Steps to reproduce

For new example requests, describe the use case and framework.

Issue titles follow [Pull request and commit titles](#pull-request-and-commit-titles):
keep the prefilled `fix:` (bug report) or `feat:` (example request) prefix.

Describe urgency and the expected scope when useful. Maintainers or triagers
assign/create the canonical `priority:` and `size:` GitHub labels; reporters do
not need label permissions.

---

## Questions?

Open a [GitHub Discussion](https://github.com/cubrid-lab/cubrid-cookbook-python/discussions)
or file an [issue](https://github.com/cubrid-lab/cubrid-cookbook-python/issues).
