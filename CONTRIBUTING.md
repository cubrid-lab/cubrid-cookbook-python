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

All non-trivial work follows the cubrid-lab 4-phase cycle. Every change to an
example ships its implementation, its tests, and its docs **together** — code
without doc updates is considered incomplete.

Contributors provide the motivation, implementation, tests, and matching docs.
Maintainers coordinate project-specific Oracle/Codex reviews, agent tooling,
labels, release classification, and integration. You do not need to install an
agent or Oracle tool to contribute; ordinary design discussion and PR review
provide the handoff to those maintainer responsibilities.

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
CI runs the same `make check` command. Both required live smoke matrix jobs also
run the Make/readiness regression guards before selecting driver dependencies.
The repository is an example collection, so `pip install -e .` is not supported.

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
  updates; it completes only after the required checks (CI Gate and smoke
  tests) pass. Major updates wait for a maintainer. The `docs-sync` and
  `translation-sync` gates skip Dependabot PRs, since dependency-only bumps
  carry no doc changes.

When a new recipe adds a `requirements.txt` outside the configured
`directories` globs, extend the globs in the same PR; the test above fails
until you do.

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
footnote's "advanced" SQLAlchemy recipes at `>=1.4.2`; `fundamentals/connect`,
`fundamentals/orm-basics` and the full example apps under `templates/` at the
`>=1.7,<2` line the drivers are actually published as; `fundamentals/pycubrid`
at `>=1.8,<2` for errno-carrying batch errors and the CAS-session fix).
`scripts/check_dependency_floors.py` (run by `make check`) fails on a bare
driver requirement, a floor below its applicable minimum, or an undocumented
custom floor — add it as a named exception in both the script and
SUPPORT_MATRIX.md instead of pinning it ad hoc.

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
installs that exact release from PyPI. Publication is retried up to six times,
with a 60-second installer timeout and 10 seconds between attempts; the maximum
requested-install budget is 410 seconds. An unavailable release fails explicitly.
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
`version`), like pushes, pull requests and the nightly schedule, is an ordinary
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

**Result.** The run's `conclusion` is `success` only when both CUBRID smoke jobs pass
and every job installed exactly the requested version from PyPI. The
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
    {"cubrid": "11.2", "request_valid": true, "installed_version": "1.8.0",
     "origin": "package index", "server": "11.2.x", "verification": "passed",
     "result": "success"},
    {"cubrid": "11.4", "…": "…"}
  ]
}
```

`status` is `success` or `failure`; `installed_version` is `null` unless every job
installed the same version, and a failure lists its `reasons` (invalid request,
missing or failed jobs, `installed X differs from requested Y`). The report job
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

The called run behaves exactly like a release dispatch: the exact PyPI install with
the bounded publication retry, no fallback to the latest release or to `main`, both
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
  `… (CUBRID 11.4)` and `… / Release verification report`, and upload the artifacts
  `release-verification-part-cubrid-11.2`, `release-verification-part-cubrid-11.4`
  and `release-verification-<request_id>`. Call the workflow at most once per
  caller run.

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
markers shown only in quotes, comments, or fenced examples. The existing
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

- All PRs require at least one review before merge.
- CI must pass (lint checks).
- Examples must be tested against a live CUBRID instance.

Explain unavailable local checks so maintainers can arrange validation. A reason
or an AI review does not waive the CI or live checks required before merge.

---

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
