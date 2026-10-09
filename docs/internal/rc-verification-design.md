# Design: verify a driver release candidate against the cookbook before PyPI publish

- **Status:** Proposed (design only; no workflow behavior changes in this PR)
- **Issue:** [#240](https://github.com/cubrid-lab/cubrid-cookbook-python/issues/240)
- **Date:** 2026-10-09
- **Affected repositories:** `cubrid-cookbook-python` (callee), `pycubrid`,
  `sqlalchemy-cubrid`, `cubrid-mcp-server` (callers)

## 1. Problem

The canonical cubrid-lab release workflow (`publish-pypi.yml` in pycubrid and
sqlalchemy-cubrid, `release.yml` in cubrid-mcp-server) runs, on a push to `main`
that bumps the version:

```text
detect -> consistency -> matrix (integration-full.yml) -> build -> publish -> verify-cookbook -> require-cookbook -> summary
```

`verify-cookbook` calls this repository's `smoke-test.yml` through
`workflow_call` **after** `publish` has created the tag, uploaded to PyPI and
published the GitHub Release. `smoke-test.yml` and `scripts/release_smoke.py`
accept only `package` + `version` and install `package==version` from
`https://pypi.org/simple`, so a candidate cannot be verified before it exists on
PyPI. A cookbook failure can therefore only mark an already-public release as
"not verified"; it cannot stop it.

### Evidence from the last release (2026-10-09, version 1.10.0 of both drivers)

| Release run | Failed cookbook cell | Cause | Passing cell duration |
| --- | --- | --- | --- |
| pycubrid [37871725585](https://github.com/cubrid-lab/pycubrid/actions/runs/37871725585) | `Smoke Tests (CUBRID 11.2)`, step *Select released drivers* | `pycubrid==1.10.0` not resolvable from the PyPI simple index for ~50 s after upload (6 attempts, `ResolutionImpossible`) | 11.4: 3 min 15 s |
| sqlalchemy-cubrid [37871732934](https://github.com/cubrid-lab/sqlalchemy-cubrid/actions/runs/37871732934) | `Smoke Tests (CUBRID 11.4)`, same step | same, for `sqlalchemy-cubrid==1.10.0` | 11.2: 3 min 19 s |

These are the "one post-publish cookbook failure" each driver's
`docs/CI_POLICY.md` records in its two-release sample. Neither was a recipe
regression: in each run the other CUBRID cell installed the same release a few
seconds later and passed. Two conclusions follow:

1. A pre-publish check against the **built artifact** removes the index
   propagation race from the gating signal entirely (no index is involved).
2. The post-publish check keeps that race. Its retry budget is a separate,
   cookbook-only fix (follow-up C4) and is out of scope here, because #240
   requires post-publish verification to stay unchanged.

The callers also pin different cookbook commits: pycubrid and sqlalchemy-cubrid
use `16f3a91` (22 commits behind `main` on 2026-10-09), cubrid-mcp-server uses
`fe01e71` (18 behind).

## 2. Goals and non-goals

Goals:

- A caller can pass the wheel its `build` job produced and get a pass/fail
  **before** `publish` runs, and `publish` depends on that result.
- The bytes verified are the bytes uploaded to PyPI.
- Post-publish verification (`verify-cookbook` / `require-cookbook`, the
  `release-verification-<request_id>` artifact and its schema) is unchanged.
- No secrets, no PAT, no new token scopes, no new schedules, minimal extra jobs.

Non-goals:

- Changing which recipes or suites the cookbook runs (#240 "Out of scope").
- Changing the drivers' own `integration-full.yml` matrix.
- Coordinated multi-package releases (see section 7.4).

## 3. Constraints

- **CI cost decisions (week of 2026-10-05):** no new weekly or full-matrix
  schedules; prefer reuse of existing workflows; keep job count minimal.
- **Cross-repo reusable workflows** are pinned by full 40-hex SHA with a
  `# main` comment and bumped by Dependabot (`github-actions` ecosystem), as
  documented in pycubrid `RELEASING.md` ("Cookbook verification").
- **Undeclared inputs are a startup failure.** A caller that passes an input
  the pinned `smoke-test.yml` does not declare makes the whole release run
  invalid before any job starts. Rollout ordering (section 9) depends on this.
- **Job timeouts:** every executing cookbook job sets `timeout-minutes`
  (`tests/test_workflow_timeouts.py`); a caller job that `uses:` a reusable
  workflow cannot set one, so the callee's job timeouts are the bound.
- **The canonical release workflow** is kept identical across the three
  callers except for the package-specific lines, so a caller change lands in
  all three repositories.

## 4. Options considered

### Option A — Artifact mode: verify the caller's built wheel from the same run (recommended)

Add two optional `workflow_call` inputs to `smoke-test.yml`:

| Input | Rule |
| --- | --- |
| `candidate_artifact` | name of an artifact uploaded earlier **in the caller's run** (for example `release-dist`); `^[A-Za-z0-9._-]{1,100}$`; empty = today's published mode |
| `candidate_hashes` | required with `candidate_artifact`: the JSON object `{"<filename>": "<sha256 hex>", ...}` the caller's `build` job already outputs (`needs.build.outputs.sha256`) |

A reusable workflow's jobs are jobs of the caller's run, so
`actions/download-artifact` in the cookbook jobs downloads the caller's
`release-dist` artifact by name with the runner's own artifact token. No token
input, no cross-run API call and no permission beyond `contents: read`.

Flow in each smoke job (`release_smoke.py select` in candidate mode):

1. Validate `package`, `version`, `request_id`, `candidate_artifact` and
   `candidate_hashes` from `RELEASE_INPUT_*` (never shell code), as today.
2. Download the artifact into `$RUNNER_TEMP/candidate/`.
3. Require exactly one wheel whose normalized name and version match
   `package`/`version` (`pycubrid-1.10.0-*.whl`,
   `sqlalchemy_cubrid-1.10.0-*.whl`, `cubrid_mcp_server-…`), recompute its
   SHA-256 and require it to equal the `candidate_hashes` entry. Any extra,
   missing or mismatching wheel fails before install.
4. `pip install <wheel>` (dependencies from PyPI), then the existing bootstrap
   with `--constraint` pinning `package==version`; export
   `PIP_FIND_LINKS=$RUNNER_TEMP/candidate` so every later install (example
   requirements, framework suites, the MCP server) can satisfy the pin from
   the candidate directory and never from the index.
5. `freeze`/`verify`/`summary` accept, **for the requested package only**, an
   origin of `candidate artifact`: `direct_url.json` must be a `file://` URL
   inside `$RUNNER_TEMP/candidate/` naming the verified wheel. Every other
   driver must still come from the package index. The publication retry loop
   is skipped (there is no publication to wait for).
6. The rest of the job (all goldens, AI-agent, Flask/FastAPI, async-worker,
   Django and dashboard suites, MCP smoke) is unchanged.

Outputs and report: the same four outputs plus a new `source` output
(`index` or `artifact`). The report JSON gains additive fields `source` and
`candidate_sha256` (no schema bump: existing consumers read the same keys). To
allow two calls in one caller run (pre- and post-publish), candidate mode uses
distinct artifact names — `release-candidate-part-cubrid-<v>` for the matrix
parts and `release-candidate-verification-<request_id>` for the report — so it
can never overwrite or be mistaken for the published-mode parts the post-publish
report downloads with `release-verification-part-*`. Published-mode names stay
as they are.

Caller shape (canonical release workflow, pycubrid shown):

```yaml
  verify-candidate:
    name: Cookbook candidate verification
    needs: [detect, build]
    if: needs.build.result == 'success'
    permissions:
      contents: read                  # all the called workflow needs
    uses: cubrid-lab/cubrid-cookbook-python/.github/workflows/smoke-test.yml@<40-hex main commit> # main
    with:
      package: pycubrid
      version: ${{ needs.detect.outputs.version }}
      request_id: pycubrid-rc-v${{ needs.detect.outputs.version }}-${{ github.run_id }}-${{ github.run_attempt }}
      candidate_artifact: release-dist
      candidate_hashes: ${{ needs.build.outputs.sha256 }}

  require-candidate:
    name: Require a verified candidate
    needs: [detect, build, verify-candidate]
    if: always() && needs.build.result == 'success'
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions: {}
    steps:
      - env:
          RESULT: ${{ needs.verify-candidate.result }}
          STATUS: ${{ needs.verify-candidate.outputs.status }}
          SOURCE: ${{ needs.verify-candidate.outputs.source }}
          REQUESTED: ${{ needs.verify-candidate.outputs.requested_version }}
          INSTALLED: ${{ needs.verify-candidate.outputs.installed_version }}
          VERSION: ${{ needs.detect.outputs.version }}
        run: |
          [ "$RESULT" = success ] && [ "$STATUS" = success ] && [ "$SOURCE" = artifact ] \
            && [ -n "$INSTALLED" ] && [ "$INSTALLED" = "$REQUESTED" ] && [ "$REQUESTED" = "$VERSION" ]

  publish:
    needs: [detect, consistency, matrix, build, require-candidate]   # was [detect, consistency, matrix, build]
```

`publish` already downloads the same `release-dist` artifact and re-checks it
against the recorded hashes, so the wheel the cookbook verified is byte for
byte the wheel uploaded to PyPI. The post-publish `verify-cookbook` and
`require-cookbook` jobs stay exactly as they are.

| Pros | Cons |
| --- | --- |
| Verifies the exact bytes that are published (hash-checked on both sides) | Requires a cookbook change to `smoke-test.yml` and `release_smoke.py`, plus a caller change in three repos |
| No index involved: removes the propagation race from the gate | Adds ~3.5 min wall time between `build` and `publish` |
| No token, no secrets, `contents: read` only; reuses the existing workflow, matrix and report | A new origin class (`candidate artifact`) in the provenance checks must be kept narrow (requested package only) |
| Works for dry-run (`--ref <branch> -f action=dry-run`) and resume (`build` re-runs) | Candidate cannot depend on another unpublished candidate (section 7.4) |

### Option B — Commit mode: the cookbook builds the driver from the tag commit

Add a `candidate_sha` input (40-hex driver commit). The cookbook installs
`<package> @ git+https://github.com/cubrid-lab/<package>.git@<sha>`, the
pattern `driver-main.yml` already uses, and accepts a `vcs_info` origin with
`commit_id == candidate_sha`.

| Pros | Cons |
| --- | --- |
| No artifact plumbing; one string input | Tests a wheel the cookbook built with its own `pip`/build backend, **not** the bytes published |
| Can start in parallel with `matrix` (needs only `detect`), so it adds no wall time on the critical path | Needs network access to the driver repo at an unpublished commit; a private fork or a rewritten history breaks it |
| Reusable for ad-hoc "test this driver commit" dispatches | Duplicates `driver-main.yml`'s install path inside the release contract; a second provenance class (`vcs`) to validate |
| | Starting before `matrix` passes spends cookbook minutes on candidates the matrix will reject |

### Option C — Stage on TestPyPI, verify from there, then publish to PyPI

The caller uploads the candidate to TestPyPI, the cookbook installs it with
`--index-url https://test.pypi.org/simple --extra-index-url https://pypi.org/simple`,
then the caller uploads to PyPI.

| Pros | Cons |
| --- | --- |
| Exercises a real index install, close to what users do | A second Trusted Publisher, environment and `id-token: write` job per repo |
| | TestPyPI versions are immutable too: a failed candidate burns the version on TestPyPI and every retry needs a new one |
| | `--extra-index-url` mixes indexes (dependency-confusion class of risk) and TestPyPI has its own propagation race — the exact failure seen on 2026-10-09 |
| | More jobs and more moving parts than A for no stronger guarantee |

### Baseline — keep post-publish only, yank on failure

Zero cost, but a yank is manual, user-visible and leaves the version burned. It
is what happens today and is what #240 asks to replace.

## 5. Recommendation

**Option A**, blocking, with post-publish verification unchanged.

It is the only option that verifies the published bytes themselves, it adds no
secret or permission, it reuses `smoke-test.yml`, its matrix and its report
contract, and it removes the failure class actually observed. Option B's
latency advantage is real but small (about 3.5 minutes on a ~12-minute release run)
and it trades away byte identity; it can be added later as a separate
`driver-main.yml` dispatch input if ad-hoc commit testing is wanted.

## 6. Scope of the candidate run

- **Recipes:** the full `smoke-test.yml` workflow-call scope, unchanged: every
  golden (`make verify`, full tree), AI-agent examples (twice), Flask/FastAPI,
  async-worker, Django and the isolated dashboard suite, and the MCP smoke.
  #240 rules out changing the test set; reusing it also means the candidate and
  post-publish runs are directly comparable.
- **CUBRID versions:** 11.2 and 11.4, the existing `smoke-test.yml` matrix and
  the cookbook's supported range. The drivers' own `integration-full.yml`
  already covers 10.2–11.4 × Python 3.11–3.14; the cookbook adds application
  realism, not more server versions. Dropping 11.2 would save one job but leave
  11.2 recipe regressions to the post-publish check, which cannot block.
- **Python:** 3.12, as today.
- **Other drivers:** resolved from PyPI. A pycubrid candidate runs with the
  latest published sqlalchemy-cubrid (and vice versa), which is what users get
  the moment the candidate is published.

## 7. Semantics

### 7.1 Blocking vs advisory

| Check | Mode | Effect on failure |
| --- | --- | --- |
| `verify-candidate` + `require-candidate` (new) | **Blocking** | `publish` does not run: no tag, no PyPI upload, no Release |
| `verify-cookbook` + `require-cookbook` (unchanged) | Blocking for the run's verdict, cannot undo publish | Release run fails; the release is reported as not verified |
| `driver-main.yml` (unchanged) | Advisory | Tracking issue only |

### 7.2 Timeouts and cost

Measured on 2026-10-09 (runs above): a passing cookbook smoke cell takes about
3 min 15 s, the report job 6–8 s, the `require-*` job 2–4 s.

| | Today | With Option A |
| --- | --- | --- |
| Jobs per release run | 34 (pycubrid) / 35 (sqlalchemy-cubrid) | +4: two smoke cells, one report, one `require-candidate` |
| Extra runner minutes per release | — | ~7 (billed ~9 with per-job rounding) |
| Wall time `build` → `publish` | ~4 s | ~3.5 min |
| Bound on the added wall time | — | callee job timeouts: 60 min (`verify`) and 5 min (`report`); the caller's `require-candidate` 5 min |
| New schedules | — | none |

Releases are rare (two per driver in the CI_POLICY sample window), so the
weekly cost is a few minutes. The 60-minute `verify` timeout is the existing
bound; it is not lowered here because the post-publish path shares it.

### 7.3 Failure handling and override

1. **Infrastructure flake** (runner, Docker pull, CUBRID start): re-run failed
   jobs (`gh run rerun <id> --failed`). `release-dist` (14-day retention) and
   the `build` hashes are reused; nothing is published yet.
   Nothing has been tagged or uploaded, so no version is burned.
2. **Real recipe failure caused by the driver:** fix the driver on `main`. The
   version was never tagged or published, but today's `resume` requires an
   existing tag (`scripts/release_detect.py`) and a push releases only when
   `__version__` changes, so P1 must add one recovery path: `resume` accepts an
   **absent** tag when `__version__` and the dated CHANGELOG section at `main`
   match the requested version, and then builds from `main` (which includes the
   fix). The alternative, with no workflow change, is to release the fix as the
   next patch version.
3. **Recipe failure caused by the cookbook** (a cookbook bug exposed by the
   candidate): fix the cookbook on `main`, bump the caller's pin in a PR to the
   driver's `main`, then use the same untagged `resume`
   (`gh workflow run publish-pypi.yml -f action=resume -f version=X.Y.Z`).
4. **Override (emergency only):** a new recovery input on the release
   workflow, `cookbook_override_reason` (non-empty free text, `resume` only,
   dispatched from `main`), makes `require-candidate` pass with a warning and
   records the reason in the release summary. It runs in the existing `pypi`
   environment, so required reviewers (where configured) approve the publish as
   today. The post-publish `verify-cookbook` still runs and is not overridable.
   This is optional: without it, path 3 is the only way through.

### 7.4 Coordinated releases (pycubrid and sqlalchemy-cubrid together)

Candidate mode installs only the requested package from the artifact; the other
driver comes from PyPI. If a sqlalchemy-cubrid candidate requires an
unpublished pycubrid (for example `pycubrid>=1.11` while PyPI has 1.10.x), its
candidate install fails at resolution. Release order is therefore pycubrid
first, then sqlalchemy-cubrid, as today; the sqlalchemy-cubrid candidate
verification then also exercises the just-published pycubrid. Verifying two
unpublished candidates together is out of scope.

## 8. Security

- **Least privilege:** the calling job grants `contents: read` only; the
  cookbook workflow's top-level `permissions` stay `contents: read`. The
  candidate jobs run before `publish`, so they are never in a job holding
  `contents: write` or `id-token: write`, and `publish` does not trust any
  output of the cookbook beyond the pass/fail gate.
- **No secrets:** no `secrets: inherit`, no PAT, no `COOKBOOK_DISPATCH_TOKEN`.
  Artifact download inside the same run uses the runner's own artifact token.
- **Pinned refs:** callers pin the cookbook by full commit SHA; every cookbook
  job checks out exactly `job.workflow_sha` (existing "Detect release workflow
  call" step), never the caller's repository or `main`.
- **Input handling:** the new inputs reach `release_smoke.py` only as
  `RELEASE_INPUT_*` environment variables, are validated by regex/JSON parsing
  before any download or install, and never enter shell code.
- **Integrity:** the wheel's SHA-256 must match the caller's `build` output,
  and `publish` re-checks the same hashes before upload. A tampered or swapped
  artifact fails one side or the other.
- **Code execution:** the candidate wheel is the caller's own build and runs in
  the same sandbox the cookbook already uses for untrusted example code
  (`persist-credentials: false`, read-only token).

## 9. Rollout

Order matters: a caller must never reference an input the pinned cookbook
commit does not declare (startup failure of the whole release run).

1. **cubrid-cookbook-python (C1–C3):** implement artifact mode, contract tests,
   and document it in CONTRIBUTING's "Release verification contract". Validate
   with the offline suites and a caller dry-run (step 2). Merge; note the
   resulting `main` SHA.
2. **pycubrid (P1):** bump the pin of both cookbook calls to that SHA, add
   `verify-candidate` + `require-candidate`, make `publish` need
   `require-candidate`. Validate with
   `gh workflow run publish-pypi.yml --ref <branch> -f action=dry-run -f version=<current __version__>`
   (#240 "Validation": a dry-run with a locally built wheel). Update
   `RELEASING.md` and `docs/CI_POLICY.md`.
3. **sqlalchemy-cubrid (S1):** the same change (canonical workflow), validated
   the same way.
4. **cubrid-mcp-server (M1):** the same change in `release.yml`; the cookbook's
   `install-mcp` path must honor candidate mode (C1).
5. **First real release** after rollout: confirm in the release summary that
   both the candidate and the post-publish reports are present and agree.

Rollback: revert the caller PR (removes the pre-publish gate); the cookbook
inputs are optional and harmless when unused.

## 10. Keeping the pinned SHA current across callers

- All callers pin the **same** cookbook `main` SHA. Dependabot
  (`github-actions`, weekly) proposes the newest `main` commit in each caller;
  merge those within the week they appear.
- A cookbook PR that changes the release contract (inputs, outputs, artifact
  names, report fields, provenance rules) is labelled as such in its PR body and
  lists the caller bump PRs as follow-ups; callers bump all their cookbook pins
  together (pre- and post-publish calls share one SHA).
- No new schedule or drift job: drift is visible in each release summary (the
  report's `run.commit` is the cookbook commit tested).

## 11. Follow-up issues (not filed by this PR)

| Id | Repository | Title | Priority / size |
| --- | --- | --- | --- |
| C1 | cubrid-cookbook-python | `feat(ci): artifact (candidate) mode for the smoke-test workflow_call contract` — `candidate_artifact` / `candidate_hashes` inputs, `source` output, hash and provenance checks in `release_smoke.py`, namespaced candidate artifacts, `install-mcp` support, CONTRIBUTING contract update | high / M |
| C2 | cubrid-cookbook-python | `test: contract tests for the candidate inputs` — extend `tests/test_release_workflow_call.py` (declared inputs/outputs, env-only data path, candidate artifact names never match `release-verification-part-*`, hash mismatch / extra wheel / wrong version fail before install, published mode unchanged) | high / S |
| C3 | cubrid-cookbook-python | `docs: pin-currency policy for release-contract callers` — section 10 in CONTRIBUTING | medium / XS |
| C4 | cubrid-cookbook-python | `fix(ci): wall-clock publication budget for post-publish verification` — the 2026-10-09 failures exhausted 6 attempts in ~50 s; use a time-based budget with backoff (separate from #240) | medium / S |
| P1 | pycubrid | `ci(release): verify the built wheel against the cookbook before publish` — `verify-candidate`, `require-candidate`, `publish` needs it, pin bump, `resume` of an untagged candidate (section 7.3), RELEASING.md and CI_POLICY.md | high / M |
| P2 | pycubrid | `ci(release): optional cookbook_override_reason recovery input` (section 7.3, step 4) | low / S |
| S1 | sqlalchemy-cubrid | same as P1 | high / M |
| S2 | sqlalchemy-cubrid | same as P2 | low / S |
| M1 | cubrid-mcp-server | same as P1 for `release.yml`; bump the pin from `fe01e71` | medium / M |
| M2 | cubrid-mcp-server | same as P2 | low / S |

## 12. Open questions

- Whether `actions/download-artifact` in a re-run attempt reliably sees
  artifacts uploaded by an earlier attempt of the same run; the pycubrid
  partial-upload recovery already relies on it, and the P1 dry-run should
  confirm it for the called jobs.
- Whether the override (P2/S2/M2) is wanted at all; the design works without it.
