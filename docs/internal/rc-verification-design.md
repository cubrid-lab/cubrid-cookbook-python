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

| Release run | PyPI upload done | Passing cell resolved the version | Failing cell still failing at | Failed cell |
| --- | --- | --- | --- | --- |
| pycubrid [37871725585](https://github.com/cubrid-lab/pycubrid/actions/runs/37871725585) | 01:59:16 | 02:00:03 (CUBRID 11.4, +47 s) | 02:00:51 (+95 s) | `Smoke Tests (CUBRID 11.2)`, step *Select released drivers* |
| sqlalchemy-cubrid [37871732934](https://github.com/cubrid-lab/sqlalchemy-cubrid/actions/runs/37871732934) | 02:00:39 | 02:01:15 (CUBRID 11.2, +36 s) | 02:02:25 (+106 s) | `Smoke Tests (CUBRID 11.4)`, same step |

(UTC. Each failing cell exhausted the 6 bounded attempts of
`release_smoke.py select` with `ResolutionImpossible`; each passing cell then
took about 3 min 15 s in total.)

These are the "one post-publish cookbook failure" each driver's
`docs/CI_POLICY.md` records in its two-release sample. Neither was a recipe
regression. The pattern is **stale data on some PyPI CDN nodes**, not a fixed
propagation delay: in the same run, one cell already resolved the new version
while the other, started at the same second, kept getting an index page
without it for up to ~95–106 s after upload. Two conclusions follow:

1. A pre-publish check against the **built artifact** removes the index from
   the gating signal entirely (no index lookup for the candidate).
2. The post-publish check keeps the stale-node exposure. Fixing it is a
   separate, cookbook-only change (follow-up C4) and is out of scope here,
   because #240 requires post-publish verification to stay unchanged.
   **C4 is implemented** (see section 11): `scripts/release_smoke.py select` now
   waits until the PyPI JSON API serves the requested version before installing.

The callers also pin different cookbook commits: pycubrid and sqlalchemy-cubrid
use `16f3a91` (22 commits behind `main` on 2026-10-09), cubrid-mcp-server uses
`fe01e71` (18 behind).

## 2. Goals and non-goals

Goals:

- A caller can pass the distribution its `build` job produced and get a
  pass/fail **before** `publish` runs, and `publish` depends on that result.
- The bytes verified are the bytes uploaded to PyPI, and that holds even
  though third-party code now runs between `build` and `publish` (section 8).
- Post-publish verification (`verify-cookbook` / `require-cookbook`, the
  `release-verification-<request_id>` artifact and its schema) is unchanged.
- No secrets, no PAT, no new token scopes, no new schedules, minimal extra jobs.

Non-goals:

- Changing which recipes or suites the cookbook runs (#240 "Out of scope").
- Changing the drivers' own `integration-full.yml` matrix.
- Verifying two unpublished candidates together (see section 7.4).

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
  all three repositories. The same holds for `scripts/release_detect.py`
  (byte-identical today except the workflow filename in its docstring) and
  `scripts/release_summary.py`: every change below to either script is made
  identically in all three repositories.

## 4. Options considered

### Option A — Artifact mode: verify the caller's built distribution from the same run (recommended)

Add optional `workflow_call` inputs to `smoke-test.yml`:

| Input | Rule |
| --- | --- |
| `candidate_artifact` | name of an artifact uploaded earlier **in the caller's run** (for example `release-dist`); `^[A-Za-z0-9._-]{1,100}$`; empty = today's published mode |
| `candidate_hashes` | required with `candidate_artifact`: the JSON object `{"<filename>": "<sha256 hex>", ...}` the caller's `build` job already outputs (`needs.build.outputs.sha256`); keys `^[A-Za-z0-9._+-]{1,200}$`, values `^[0-9a-f]{64}$` |
| `candidate_artifact_id` | optional: the numeric `artifact-id` output of the caller's `upload-artifact` step; when set, the artifact is downloaded by ID instead of by name (section 8.1) |

A reusable workflow's jobs are jobs of the caller's run, so
`actions/download-artifact` in the cookbook jobs downloads the caller's
artifact with the runner's own job-scoped artifact token. No token input, no
cross-run API call and no permission beyond `contents: read`.

Flow in each smoke job (`release_smoke.py select` in candidate mode):

1. Validate `package`, `version`, `request_id` and the candidate inputs from
   `RELEASE_INPUT_*` (never shell code), as today.
2. Download the artifact into `$RUNNER_TEMP/candidate/` (by ID when
   `candidate_artifact_id` is set). The files must land directly in that
   directory. Where a by-ID download lands depends on the
   `actions/download-artifact` version. From v5.0.0 on, a single by-ID
   download counts as a single-artifact download (`artifacts.length === 1`
   in `src/download-artifact.ts`) and extracts directly into `path`. Up to
   v4.3.0 only a download by `name` counted (`isSingleArtifactDownload =
   !!inputs.name`), so a by-ID download extracted into
   `path/<artifact-name>/` unless `merge-multiple: true` was set. Since
   cookbook #195, `smoke-test.yml` pins v8.0.1, the version the callers'
   `publish` job already pins, so C1's single by-ID download extracts
   directly into `$RUNNER_TEMP/candidate/` with no extra input. Because this
   depends on the action version, a future change of that pin must keep it
   (C2 asserts where the files land). `name` and
   `artifact-ids` cannot be combined (the action rejects it), so the by-ID
   download passes no `name`.
3. **Check the whole file set.** The set of downloaded file names must equal
   the set of `candidate_hashes` keys exactly (the caller's `release-dist`
   holds the wheel **and** the sdist), and every file's recomputed SHA-256,
   sdist included, must equal its entry. Any extra, missing or mismatching
   file fails before anything is installed.
4. Among those files, require exactly one wheel whose normalized name and
   version match `package`/`version` (`pycubrid-1.10.0-*.whl`,
   `sqlalchemy_cubrid-1.10.0-*.whl`, `cubrid_mcp_server-…`). **Only the wheel
   is installed**; the sdist is hash-checked but never built or installed.
5. `pip install <wheel>` (dependencies from PyPI), then the existing bootstrap
   with `--constraint` pinning `package==version`; export
   `PIP_FIND_LINKS=$RUNNER_TEMP/candidate` so every later install (example
   requirements, framework suites, the MCP server) can satisfy the pin from
   the candidate directory and never from the index. The publication retry
   loop is skipped (there is no publication to wait for).
6. `freeze`/`verify`/`summary` accept, **for the requested package only**, an
   origin of `candidate artifact`: its `direct_url.json` must exist and be a
   `file://` URL inside `$RUNNER_TEMP/candidate/` naming the verified wheel.
   In candidate mode a **missing** `direct_url.json` for the requested package
   is a failure. pip writes that file only for a direct install such as the
   wheel path of step 5, so its absence means the package came from an index
   or was resolved from the find-links directory instead. Either way the
   check fails, so the fail-safe behaviour does not change.
   The sdist sits in the same `PIP_FIND_LINKS` directory, so a later forced
   reinstall of the requested package (`--force-reinstall`, or an upgrade a
   suite triggers) could resolve to the sdist and build it. That install
   records a `direct_url.json` that is absent or names the sdist rather than
   the verified wheel, so the provenance rule fails the job. A wrong origin
   therefore fails safely; it never passes as the verified wheel.
   Every other driver must still come from the package index, exactly as in
   published mode.
7. The rest of the job (all goldens, AI-agent, Flask/FastAPI, async-worker,
   Django and dashboard suites, MCP smoke) is unchanged.

Outputs and report: the same four outputs plus a new `source` output
(`index` or `artifact`). Each part artifact and the report JSON gain the
additive fields `source` and `candidate_sha256` (the verified wheel's digest;
no schema bump: existing consumers read the same keys). In candidate mode
`build_report` requires every part to carry the same `candidate_sha256`, equal
to the wheel's entry in `candidate_hashes`; a part with a different or missing
digest fails the report. To allow two calls in one caller run (pre- and
post-publish), candidate mode uses distinct artifact names —
`release-candidate-part-cubrid-<v>[-py<p>]` for the matrix parts (the same
scheme as the published-mode `release-verification-part-cubrid-<v>[-py<p>]`,
so `-py3.11` is added only for the non-default Python cell of #268) and
`release-candidate-verification-<request_id>` for the report — so it can never
overwrite or be mistaken for the published-mode parts the post-publish report
downloads with `release-verification-part-*`. Published-mode names stay as
they are. The candidate part and report uploads keep `overwrite: true`, as the
published-mode uploads do since #188, so a `gh run rerun <id> --failed` of a
candidate cell can replace its own part from the earlier attempt. CONTRIBUTING's "Call the workflow at most once per caller run" is
relaxed explicitly to "at most once per mode per caller run" (one candidate
call and one published call).

Caller shape (canonical release workflow, pycubrid shown):

```yaml
  build:
    outputs:
      sha256: ${{ steps.hashes.outputs.sha256 }}            # existing: dist/ file -> digest
      meta_sha256: ${{ steps.hashes.outputs.meta_sha256 }}  # new, required: release-meta/ file -> digest
      dist_artifact_id: ${{ steps.upload-dist.outputs.artifact-id }}   # new, optional (section 8.1)
    # "Record SHA-256 hashes" writes release-meta/SHA256SUMS first, then emits
    # meta_sha256 over every file in release-meta/ (RELEASE_NOTES.md,
    # sbom.spdx.json, SHA256SUMS); nothing writes to release-meta/ after it.

  verify-candidate:
    name: Cookbook candidate verification
    needs: [detect, build]
    # Skipped only when completing a partial publish (tag already at the
    # release commit); see section 7.3, step 5.
    if: >-
      needs.build.result == 'success' &&
      !(needs.detect.outputs.publish == 'true' && needs.detect.outputs.tag_state == 'same')
    permissions:
      contents: read                  # required; `{}` is a startup failure (section 12)
    uses: cubrid-lab/cubrid-cookbook-python/.github/workflows/smoke-test.yml@<40-hex main commit> # main
    with:
      package: pycubrid
      version: ${{ needs.detect.outputs.version }}
      request_id: pycubrid-rc-v${{ needs.detect.outputs.version }}-${{ github.run_id }}-${{ github.run_attempt }}
      candidate_artifact: release-dist
      candidate_artifact_id: ${{ needs.build.outputs.dist_artifact_id }}
      candidate_hashes: ${{ needs.build.outputs.sha256 }}

  require-candidate:
    name: Require a verified candidate
    needs: [detect, build, verify-candidate]
    if: "!cancelled() && needs.build.result == 'success'"
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
          PUBLISH: ${{ needs.detect.outputs.publish }}
          TAG_STATE: ${{ needs.detect.outputs.tag_state }}
        run: |
          if [ "$PUBLISH" = true ] && [ "$TAG_STATE" = same ] && [ "$RESULT" = skipped ]; then
            echo "::notice::tag already at the release commit; completing a partial publish without the candidate gate"
            exit 0
          fi
          [ "$RESULT" = success ] && [ "$STATUS" = success ] && [ "$SOURCE" = artifact ] \
            && [ -n "$INSTALLED" ] && [ "$INSTALLED" = "$REQUESTED" ] && [ "$REQUESTED" = "$VERSION" ]

  publish:
    needs: [detect, consistency, matrix, build, require-candidate]   # was [detect, consistency, matrix, build]
    # was: if: needs.detect.outputs.publish == 'true'
    # A status function is required here: without one the condition is an
    # implicit success() over all of publish's ancestors, and verify-candidate
    # is skipped on a tagged resume (section 7.3, step 5).
    if: >-
      !cancelled() && needs.detect.outputs.publish == 'true' &&
      needs.consistency.result == 'success' && needs.matrix.result == 'success' &&
      needs.build.result == 'success' && needs.require-candidate.result == 'success'
    steps:
      - name: Check out the release scripts       # sparse checkout gains one script
        uses: actions/checkout@<pinned>
        with:
          ref: ${{ github.sha }}
          sparse-checkout: |
            scripts/pypi_duplicate_guard.py
            scripts/verify_dist.py
          sparse-checkout-cone-mode: false
          persist-credentials: false
      # ... download release-dist into dist/ and release-meta into release-meta/
      # (by ID when the build job outputs an artifact ID), then, BEFORE the tag
      # step and before "Create the draft GitHub Release":
      - name: Check dist/ and release-meta/ against the build job outputs
        env:
          DIST_SHA256: ${{ needs.build.outputs.sha256 }}
          META_SHA256: ${{ needs.build.outputs.meta_sha256 }}
        run: |
          python3 scripts/verify_dist.py --dir dist --expected-env DIST_SHA256
          python3 scripts/verify_dist.py --dir release-meta --expected-env META_SHA256
      # The existing `sha256sum --strict -c ../release-meta/SHA256SUMS` step may
      # stay after it as a redundant check; SHA256SUMS is now itself verified.

  summary:
    needs: [detect, consistency, matrix, build, verify-candidate, require-candidate, publish, verify-cookbook, require-cookbook]
```

`scripts/verify_dist.py` (new, standard library only, kept identical across
the three callers like `pypi_duplicate_guard.py`) reads the JSON map from the
named environment variable and fails unless: the map parses as a non-empty
JSON object whose keys are plain file names and whose values are 64-character
lowercase hex digests; the directory holds only regular files (no
subdirectory, no symlink); the set of file names equals the set of map keys
exactly; and every file's SHA-256 equals its entry. It runs before
`pypi_duplicate_guard.py`, which removes from `dist/` the files PyPI already
serves, so it always sees the full build output. Keeping the check in a
script, not inline Python in the workflow, gives it unit tests
(`tests/test_verify_dist.py`; section 11, P1).

The integrity argument rests on the `build` job outputs `sha256` and
`meta_sha256`, not on any artifact. Today `publish` checks `dist/` only
against `release-meta/SHA256SUMS`, which is itself an artifact, and does not
check `RELEASE_NOTES.md` or `sbom.spdx.json` at all before attaching them to
the GitHub Release. With Option A, jobs that run unpinned third-party code
execute in the same run between `build` and `publish`, and any job in a run
can replace a same-named artifact of that run (section 8.1). A job output, by
contrast, is fixed when the `build` job finishes and cannot be changed by a
later job. So the required change, in P1, S1 and M1, is:

- `build` emits a second job output, `meta_sha256`, mapping every file of
  `release-meta/` (`RELEASE_NOTES.md`, `sbom.spdx.json`, and `SHA256SUMS`,
  which stays) to its SHA-256, alongside the existing `sha256` for `dist/`;
- **before the tag step**, so before "Create the draft GitHub Release",
  `publish` runs `scripts/verify_dist.py` on `dist/` against
  `needs.build.outputs.sha256` and on `release-meta/` against
  `needs.build.outputs.meta_sha256`. For both directories the file set must
  equal the map keys exactly and every digest must match. Both checks are
  required.

The `SHA256SUMS` check may stay as a redundant check, but it is no longer the
trust anchor. Downloading by `artifact-id` (the `build` job outputs it; both
the cookbook and `publish` download by that ID) is an optional second layer: a
replaced artifact gets a new ID. With the required checks in place, the wheel
the cookbook verified and the files uploaded to PyPI are byte for byte the
files `build` hashed, and the notes and SBOM attached to the GitHub Release
are the ones `build` produced. The post-publish `verify-cookbook` and
`require-cookbook` jobs stay exactly as they are.

| Pros | Cons |
| --- | --- |
| Verifies the exact bytes that are published (both sides checked against the immutable `build` outputs) | Requires a cookbook change to `smoke-test.yml` and `release_smoke.py`, plus a caller change in three repos (including `meta_sha256` and the `publish` checks in `scripts/verify_dist.py`) |
| No index involved: removes the stale-CDN failure class from the gate | Adds ~3.5 min wall time between `build` and `publish` |
| No token, no secrets, `contents: read` only; reuses the existing workflow, matrix and report | Third-party code runs in the release run before `publish` (threat model in section 8.1) |
| Works for dry-run (`--ref <branch> -f action=dry-run`) and for the untagged `resume` of section 7.3 | A new origin class (`candidate artifact`) in the provenance checks must be kept narrow (requested package only); a candidate cannot depend on another unpublished candidate (section 7.4) |

### Variant A2 — `build` stops waiting for `matrix`, so the candidate check runs in parallel

Change `build` from `needs: [detect, matrix]` to `needs: [detect, consistency]`;
`verify-candidate` then starts about 30 s after `consistency` and runs
alongside the ~7-minute `matrix`, and `publish` still needs `matrix`, `build`
and `require-candidate`. The candidate check would add almost nothing to the
critical path (it finishes inside the matrix window), with the same jobs and
the same integrity rule.

**Rejected for the first rollout.** The saving is about 3.5 minutes of wall
time on a release that happens a few times a month, while the cost moves the
wrong way: every release whose matrix fails would still spend about 14 counted
cookbook minutes (the CI cost decisions favour not spending minutes on a
candidate already rejected), and the "matrix gates everything after it"
invariant that `RELEASING.md`, the `build` job comment and the ordered
`PRE_PUBLISH` reporting in `scripts/release_summary.py` rely on would have to
be rewritten in three repositories. It is a one-line `needs:` change and can
be adopted later if release latency starts to matter; the integrity argument
does not change, because it rests on the `build` job outputs either way.

### Option B — Commit mode: the cookbook builds the driver from the release commit

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
| | `--extra-index-url` mixes indexes (dependency-confusion class of risk) and TestPyPI has its own CDN staleness — the exact failure class seen on 2026-10-09 |
| | More jobs and more moving parts than A for no stronger guarantee |

### Baseline — keep post-publish only, yank on failure

Zero cost, but a yank is manual, user-visible and leaves the version burned. It
is what happens today and is what #240 asks to replace.

## 5. Recommendation

**Option A** (sequential, not Variant A2), blocking, with post-publish
verification unchanged, **and** the `publish` checks of both `release-dist`
and `release-meta` moved onto the `build` job outputs (`sha256` and the new
`meta_sha256`).

It is the only option that verifies the published bytes themselves, it adds no
secret or permission, it reuses `smoke-test.yml`, its matrix and its report
contract, and it removes the failure class actually observed. Option B's
latency advantage is real but small (about 3.5 minutes on a ~12-minute release
run) and it trades away byte identity; it can be added later as a separate
`driver-main.yml` dispatch input if ad-hoc commit testing is wanted. Option A
is only sound together with the `publish` change in section 4: without it,
adding pre-publish third-party code to the run would weaken today's integrity
instead of strengthening it.

## 6. Scope of the candidate run

- **Recipes:** the full `smoke-test.yml` workflow-call scope, unchanged: every
  golden (`make verify`, full tree), AI-agent examples (twice), Flask/FastAPI,
  async-worker, Django and the isolated dashboard suite, and the MCP smoke.
  #240 rules out changing the test set; reusing it also means the candidate and
  post-publish runs are directly comparable.
- **Cells:** the three release cells of the existing `smoke-test.yml`
  matrix (#268), unchanged:
  - CUBRID 11.2, Python 3.12;
  - CUBRID 11.4, Python 3.12;
  - CUBRID 11.4, Python 3.11 (the supported minimum Python; added for release
    verification only).

  These are `RELEASE_CELLS` in `scripts/release_smoke.py`, and a release
  report fails unless each of them reported exactly once; the candidate
  report keeps that rule (C2). CUBRID 11.2 and 11.4 are the cookbook's
  supported range. The drivers' own `integration-full.yml` already covers
  10.2–11.4 × Python 3.11–3.14; the cookbook adds application realism, not
  more server versions. Dropping 11.2 would save one job but leave 11.2
  recipe regressions to the post-publish check, which cannot block.
- **Distribution files:** every file of the artifact is hash-checked (wheel and
  sdist); only the wheel is installed.
- **Other drivers:** resolved from PyPI. A pycubrid candidate runs with the
  latest published sqlalchemy-cubrid (and vice versa), which is what users get
  the moment the candidate is published.

## 7. Semantics

### 7.1 Blocking vs advisory

| Check | Mode | Effect on failure |
| --- | --- | --- |
| `verify-candidate` + `require-candidate` (new) | **Blocking** | `publish` does not run: no tag, no PyPI upload, no Release |
| `publish` checks of `dist/` against `needs.build.outputs.sha256` and of `release-meta/` against `needs.build.outputs.meta_sha256` (changed, required) | **Blocking** | `publish` stops before the tag step, so before the draft GitHub Release |
| `verify-cookbook` + `require-cookbook` (unchanged) | Blocking for the run's verdict, cannot undo publish | Release run fails; the release is reported as not verified |
| `driver-main.yml` (unchanged) | Advisory | Tracking issue only |

### 7.2 Timeouts and cost

Measured on 2026-10-09 (runs above): a passing cookbook smoke cell takes about
3 min 15 s, the report job 6–8 s, the `require-*` job 2–4 s.

| | Today | With Option A |
| --- | --- | --- |
| Jobs per release run | 32 (pycubrid) / 33 (sqlalchemy-cubrid) at the current pin `16f3a91` (two post-publish smoke cells); 33 / 34 once the pin is at `ec0184a` (#268) or later | +5: three smoke cells, one report, one `require-candidate` (38 / 39 in total) |
| Extra runner minutes per release | — | about 10.5 (about 14 counted with per-job rounding up to whole minutes: 4 + 4 + 4 + 1 + 1; the repositories are public, so these are counted, not billed) |
| Wall time `build` → `publish` | ~4 s | ~3.5 min |
| Bound on the added wall time | — | callee job timeouts: 60 min (`verify`) and 5 min (`report`); the caller's `require-candidate` 5 min |
| New schedules | — | none |

The P1/S1/M1 pin bump to the shared SHA (`ec0184a` or later) also adds the
11.4 / Python 3.11 cell to the **post-publish** call (one job, about 4 counted
minutes). That cost comes from the pin bump and #268, not from Option A, and
it is in the "Today" column above once the pin is current.

Releases are rare (two per driver in the CI_POLICY sample window), so the
weekly cost is a few minutes. The 60-minute `verify` timeout is the existing
bound; it is not lowered here because the post-publish path shares it.

### 7.3 Failure handling and override

1. **Infrastructure flake** (runner, Docker pull, CUBRID start): re-run failed
   jobs (`gh run rerun <id> --failed`). `build` is not re-run, so
   `release-dist` and `release-meta` (14-day retention), the artifact ID and
   the `build` hash outputs are reused (section 12); nothing is published yet,
   so no version is burned. Recovery must use `--failed`, not a full re-run:
   `build`'s `upload-artifact` steps set no `overwrite`, so a re-run `build`
   would collide with the same-named artifacts the first attempt uploaded.
2. **Real recipe failure caused by the driver:** fix the driver on `main` and
   **always release the fix as the next patch version** (X.Y.Z+1) through a
   normal release PR. X.Y.Z was never tagged or published, so nothing is
   yanked, but it is not resumed either: the reviewed X.Y.Z commit is the one
   that failed, and a new version keeps "version = reviewed release commit"
   true. The CHANGELOG can note that X.Y.Z was never published.
3. **Recipe failure caused by the cookbook** (a cookbook bug exposed by the
   candidate; the driver is fine): fix the cookbook on `main`, bump the
   caller's pin in a PR to the driver's `main` (it does not change
   `__version__`, so its push is "no release"), then dispatch an untagged
   `resume` from `main`
   (`gh workflow run publish-pypi.yml -f action=resume -f version=X.Y.Z`; in
   cubrid-mcp-server, `gh workflow run release.yml -f action=resume -f version=X.Y.Z`).
   P1/S1/M1 extend `resume` in `scripts/release_detect.py` for this case only:
   - the release content is **exactly the commit on `main` where
     `__version__` first became X.Y.Z** (the release-PR merge commit, found on
     the first-parent history of `origin/main`; ambiguity is an error), never
     the `main` head;
   - tag `vX.Y.Z` must be **absent** (an existing tag keeps today's `resume`
     path unchanged);
   - X.Y.Z must be **absent on PyPI** (checked with the JSON API, fail closed
     on any error other than "not found");
   - CHANGELOG.md at that commit must have the dated `## [X.Y.Z] - YYYY-MM-DD`
     section;
   - X.Y.Z must **still be current**: `__version__` at the `origin/main` head
     must still be X.Y.Z. Otherwise a later release PR has merged, and
     resuming X.Y.Z (for example one that failed for a driver reason and was
     superseded by X.Y.Z+1, path 2) would publish an older version after a
     newer one. This is stricter than "no tag exists for a higher version",
     which would miss a higher version whose own release run failed before
     tagging, so the version rule is the one implemented.

   The workflow file and therefore the cookbook pin come from the current
   `main` (the dispatched commit, `github.sha`), as release tooling already
   does today for `resume`; only the release content comes from the detected
   commit. `release_detect.py` stays identical across the three repositories.
4. **Override (emergency only):** a new recovery input on the release
   workflow, `cookbook_override_reason` (non-empty free text, `resume` only,
   dispatched from `main`), makes `require-candidate` pass with a warning and
   records the reason in the release summary. The post-publish
   `verify-cookbook` still runs and is not overridable. **Gating today:** the
   `pypi` environment of all three callers has no required reviewers, only a
   deployment branch policy (`main`). As things stand the override would
   therefore be **self-service for anyone who can dispatch the workflow**
   (repository write access). Recommendation: the maintainer configures
   required reviewers on the `pypi` environment before P2/S2/M2 land, so an
   override (and every publish) needs a second person. That is a repository
   settings change for the maintainer, not part of these PRs; if it is not
   made, P2/S2/M2 must document the override as self-service. The override is
   optional: without it, path 3 is the only way through a cookbook-caused
   failure.
5. **Tagged resume (completing a partial publish):** when
   `needs.detect.outputs.publish == 'true'` and `tag_state == same` (today's
   `resume` with an existing tag, or a push whose tag already points at the
   release commit), `verify-candidate` is **skipped** and `require-candidate`
   passes with a notice (caller shape in section 4).
   **Skip propagation:** a job-level `if:` that contains no status function
   (`success()`, `always()`, `failure()`, `cancelled()`) is evaluated as
   `success() && <condition>`, and `success()` is false when any job in the
   job's `needs` chain (transitively) was skipped or failed. `publish`
   depends on `require-candidate`, which depends on `verify-candidate`, so a
   skipped `verify-candidate` would skip `publish` too, even though
   `require-candidate` itself ran and passed. `require-candidate` therefore
   uses `!cancelled() && needs.build.result == 'success'`, and `publish`
   uses `!cancelled()` plus an explicit `result == 'success'` for each of
   `consistency`, `matrix`, `build` and `require-candidate`, so only those
   results gate it. Reasoning for the skip: once the
   rollout is in place, `publish` creates the tag only after
   `require-candidate` has passed, so a tag at the release commit means the
   candidate gate already passed for this version (or the release predates
   the rollout). More importantly, the version is already partly public: the
   tag exists and some files may already be on PyPI. Blocking completion on a
   cookbook failure at that point would not protect users; it would only
   leave a half-published release. The post-publish `verify-cookbook` still
   runs and still reports. Dry-run is unaffected (`publish` is `false`, so the
   candidate check runs whatever the tag state), and the untagged resume of
   path 3 has `tag_state == absent`, so the gate runs.
   No dry-run reaches `publish`, so the new `scripts/verify_dist.py` steps
   first run on a real release. That is fail-safe: they run before the tag
   step, so a failure there leaves nothing tagged or uploaded, and the
   untagged resume of path 3 recovers once the cause is fixed.

### 7.4 Coordinated releases (pycubrid and sqlalchemy-cubrid together)

Candidate mode installs only the requested package from the artifact; the other
driver comes from PyPI. If a sqlalchemy-cubrid candidate requires an
unpublished pycubrid (for example `pycubrid>=1.11` while PyPI has 1.10.x), its
candidate install fails at resolution and nothing is published.

Release PRs that depend on each other must therefore **merge sequentially**:
merge the pycubrid release PR, wait until its release run has published (and
`pip index versions pycubrid` shows the new version), then merge the
sqlalchemy-cubrid release PR, whose candidate verification then also exercises
the just-published pycubrid. Independent release PRs may still merge together,
as on 2026-10-09, when both 1.10.0 release runs started within seconds of each
other. Verifying two unpublished candidates together is out of scope.

## 8. Security

- **Least privilege:** the calling job grants `contents: read` only; the
  cookbook workflow's top-level `permissions` stay `contents: read`. The
  candidate jobs never hold `contents: write` or `id-token: write`, and
  `publish` trusts no output of the cookbook beyond the pass/fail gate.
- **No secrets:** no `secrets: inherit`, no PAT, no `COOKBOOK_DISPATCH_TOKEN`.
  Artifact download inside the same run uses the runner's own artifact token.
- **Pinned refs:** callers pin the cookbook by full commit SHA; every cookbook
  job checks out exactly `job.workflow_sha` (existing "Detect release workflow
  call" step), never the caller's repository or `main`.
- **Input handling:** the new inputs reach `release_smoke.py` only as
  `RELEASE_INPUT_*` environment variables, are validated by regex/JSON parsing
  before any download or install, and never enter shell code.
- **Integrity:** both the cookbook and `publish` check the full `release-dist`
  file set and every digest against `needs.build.outputs.sha256`, and
  `publish` checks the full `release-meta` file set (`RELEASE_NOTES.md`,
  `sbom.spdx.json`, `SHA256SUMS`) and every digest against
  `needs.build.outputs.meta_sha256`, before the tag step. Both are immutable
  job outputs and both checks are required, so no artifact is a trust anchor
  (section 8.1).
- **Provenance:** in candidate mode the requested package must have a
  `direct_url.json` pointing at the verified wheel; its absence is a failure.

### 8.1 Threat model: unpinned dependencies in the same run as the publish job

What changes. The cookbook jobs install unpinned packages from PyPI (pandas,
matplotlib, Flask, FastAPI, Django, Streamlit, every example's requirements)
and run example code. Under `workflow_call` those jobs are jobs of the
**caller's** release run — the run whose `publish` job holds
`id-token: write` (PyPI Trusted Publishing) and `contents: write`. The
`matrix` and the post-publish call already run third-party code in that run;
Option A is the first to run such a broad, unpinned set **between `build` and
`publish`**, so a compromised dependency would be in a position to tamper with
what `publish` reads.

What such code can reach (high level only):

- **Not the publish credentials.** The OIDC token request credential is
  provided only to jobs that declare `id-token: write`, and the
  `contents: write` token belongs to the `publish` job. The candidate jobs run
  on separate runners with a read-only token and no secrets.
- **The job-scoped artifact/cache token.** Every job receives a runtime token
  that lets the actions in that job upload and download the run's artifacts and
  read and write the Actions cache. Code running in the job can obtain it, so
  for that token's lifetime it can act on the **run's** artifacts: upload new
  ones and replace an existing artifact of the same name (the same mechanism
  `upload-artifact`'s `overwrite: true` uses). That includes `release-dist` and
  `release-meta` (`SHA256SUMS`, release notes, SBOM). This is why neither
  artifact can be the trust anchor for `publish`, and why each is checked
  against its own `build` job output.
- **The cache.** `smoke-test.yml` restores and, on a key miss, **saves**
  `~/.cache/pip` with `actions/cache`. Under `workflow_call` that cache belongs
  to the **caller** repository and the caller's ref (`main` for a release), so
  an entry written by a candidate job is restored by later cookbook calls in
  that repository (the post-publish call, the next release's candidate check).
  `publish` itself uses no cache.

Mitigations (required unless marked optional):

1. `publish` verifies `dist/` against `needs.build.outputs.sha256` before the
   tag step: exact file-set equality and every digest (P1/S1/M1). A replaced
   `release-dist` then fails the run before anything is tagged or uploaded.
2. `build` outputs `meta_sha256` for every file of `release-meta/`, and
   `publish` verifies `release-meta/` against it before the tag step, so
   before "Create the draft GitHub Release": exact file-set equality and every
   digest (P1/S1/M1). A replaced `release-meta` (notes, SBOM or `SHA256SUMS`)
   fails the run before anything is tagged or attached to a Release.
3. The cookbook verifies the same `release-dist` file set and digests from the
   same job output before installing anything (C1), so the bytes it tests are
   the bytes `publish` accepts.
4. Optional: `build` outputs the `artifact-id` of the `release-dist` upload
   (and, if wanted, of `release-meta`), and both the cookbook and `publish`
   download by ID (`artifact-ids` input of `actions/download-artifact`; at the
   pinned v8.0.1, as with any v5+, a single by-ID download lands directly in
   `path`; see section 4, step 2). A replaced artifact has a different ID. This is defence in depth
   only; mitigations 1 and 2 are the trust anchor.
5. In candidate mode the cookbook does not **save** the pip cache: it uses
   `actions/cache/restore` only (or `PIP_NO_CACHE_DIR=1`), so the honest
   candidate workflow cannot accidentally seed the caller's cache with an
   entry built while resolving against a candidate (C1). This does **not**
   stop malicious code: see residual risk. Published mode is unchanged by
   #240; whether it should also stop saving is a separate cookbook decision.
6. The candidate jobs keep `persist-credentials: false`, `contents: read` and
   no secrets, and never run in a job that holds a publish credential.

Residual risk:

- A compromised dependency can still make the candidate check fail or pass
  dishonestly (a gate result is only as trustworthy as the code it runs), and
  can still do whatever it can do today in the post-publish call.
- Malicious code in any candidate job can obtain the job's runtime token and
  **write Actions cache entries** for the caller repository and ref directly,
  whatever the workflow's own cache steps do; restore-only (mitigation 5)
  removes accidental seeding, not this. The same exposure already exists
  today: the post-publish call and the `matrix` run third-party code in the
  same release run with the same kind of token. A poisoned entry can affect
  later jobs that restore that cache (later cookbook calls), not the release
  bytes: `build` and `publish` use no cache.
- It cannot change the bytes uploaded to PyPI, or the notes and SBOM attached
  to the GitHub Release, without failing mitigation 1 or 2.

## 9. Rollout

Order matters: a caller must never reference an input the pinned cookbook
commit does not declare (startup failure of the whole release run).

1. **cubrid-cookbook-python (C1–C3):** implement artifact mode, contract tests,
   and document it in CONTRIBUTING's "Release verification contract"
   (including the relaxed "at most once per mode per caller run" rule).
   Validate with the offline suites and a caller dry-run **before the C1
   merge**: a throwaway pycubrid branch with the P1 change pins
   `smoke-test.yml` to the **unmerged C1 branch head SHA** (pushed to
   `cubrid-lab/cubrid-cookbook-python` so the caller can resolve it), and is
   dispatched as in step 2. That branch is never merged; it exists only to
   prove the contract end to end. Then merge C1, note the resulting `main`
   SHA, and use that SHA (with the `# main` comment) in P1/S1/M1.
2. **pycubrid (P1):** see the P1 row in section 11. Validate with
   `gh workflow run publish-pypi.yml --ref <branch> -f action=dry-run -f version=<current __version__>`
   (#240 "Validation": a dry-run with a locally built wheel). A dry-run
   never runs `publish`, so it does not exercise the `verify_dist.py` steps;
   their unit tests cover them until the first real release (section 7.3,
   step 5).
3. **sqlalchemy-cubrid (S1):** the same change (canonical workflow), validated
   the same way.
4. **cubrid-mcp-server (M1):** the same change in `release.yml`; the cookbook's
   `install-mcp` path must honor candidate mode (C1).
5. **First real release** after rollout: confirm in the release summary that
   both the candidate and the post-publish reports are present and agree.

Rollback: revert the caller PR (removes the pre-publish gate); the cookbook
inputs are optional and harmless when unused. The `publish` checks of
`release-dist` and `release-meta` against the `build` outputs are worth keeping
even after a rollback.

## 10. Keeping the pinned SHA current across callers

- All callers pin the **same** cookbook `main` SHA. Dependabot
  (`github-actions`, weekly) proposes the newest `main` commit in each caller;
  merge those within the week they appear.
- A cookbook PR that changes the release contract (inputs, outputs, artifact
  names, report fields, provenance rules) is labelled as such in its PR body and
  lists the caller bump PRs as follow-ups; callers bump all their cookbook pins
  together (pre- and post-publish calls share one SHA).
- Reconciling Dependabot with the "same SHA" policy: Dependabot runs per
  repository at different times, so the three callers can be offered
  different `main` commits in the same week. The bump that wins is the newest
  cookbook `main` commit offered to any caller: retarget the other callers'
  bump PRs to that SHA (edit the PR branch, or close it and bump by hand with
  the same `# main` comment) and merge the three together. Within one caller,
  the pre- and post-publish `smoke-test.yml` references name the same
  workflow, and Dependabot bumps every reference to it in one PR; a
  hand-made bump must do the same. P1/S1/M1 add a test that collects every
  `smoke-test.yml@` reference in the caller workflow, asserts exactly one
  distinct SHA, and requires each such line to end with `# main`;
  `COOKBOOK_SMOKE.match` applies to `verify-candidate["uses"]` as well as
  `verify-cookbook["uses"]`. That test covers one repository only: sameness
  **across** the three callers stays a manual policy (this section).
- Current move: the three callers still pin `16f3a91` (pycubrid,
  sqlalchemy-cubrid) and `fe01e71` (cubrid-mcp-server). The shared target is
  `ec0184a` (#268) or a later `main` commit, applied in all three together,
  at the latest in P1/S1/M1.
- No new schedule or drift job: drift is visible in each release summary (the
  report's `run.commit` is the cookbook commit tested).

## 11. Follow-up issues (not filed by this PR)

| Id | Repository | Title | Priority / size |
| --- | --- | --- | --- |
| C1 | cubrid-cookbook-python | `feat(ci): artifact (candidate) mode for the smoke-test workflow_call contract` — `candidate_artifact` / `candidate_hashes` / optional `candidate_artifact_id` inputs; `source` output; by-ID download whose files land directly in `$RUNNER_TEMP/candidate/` (automatic with the pinned `actions/download-artifact` v8.0.1 since #195, as with any v5+; the behaviour depends on the action version, so a future pin change must keep it in mind); exact file-set and every-digest check (sdist included), wheel-only install; candidate provenance (missing `direct_url.json` fails; a forced reinstall that resolves to the sdist in the `PIP_FIND_LINKS` directory therefore fails safely); namespaced candidate artifacts `release-candidate-part-cubrid-<v>[-py<p>]` and `release-candidate-verification-<request_id>`, uploaded with `overwrite: true` (#188) so `gh run rerun --failed` works; `candidate_sha256` on every part, matched by `build_report`; restore-only pip cache in candidate mode; `install-mcp` support; CONTRIBUTING contract update relaxing "at most once per caller run" to "once per mode" | high / M |
| C2 | cubrid-cookbook-python | `test: contract tests for the candidate inputs` — extend `tests/test_release_workflow_call.py` (declared inputs/outputs, env-only data path, candidate artifact names never match `release-verification-part-*`; by-ID download passes no `name`, uses `actions/download-artifact` v5 or later (v8.0.1 today) and its files land directly in `$RUNNER_TEMP/candidate/`; the candidate report requires all three `RELEASE_CELLS` (11.2/3.12, 11.4/3.12, 11.4/3.11), each exactly once; extra file, missing file, sdist or wheel digest mismatch, wrong version fail before install; missing `direct_url.json` fails; parts with differing `candidate_sha256` fail the report; no cache save in candidate mode; published mode unchanged) | high / S |
| C3 | cubrid-cookbook-python | `docs: pin-currency policy for release-contract callers` — section 10 in CONTRIBUTING | medium / XS |
| C4 | cubrid-cookbook-python | **Implemented** in [`scripts/release_smoke.py`](../../scripts/release_smoke.py) (`wait_for_pypi`, tested by [`tests/test_release_pypi_wait.py`](../../tests/test_release_pypi_wait.py); contract in [CONTRIBUTING.md, "Release smoke dependencies"](../../CONTRIBUTING.md#release-smoke-dependencies)): a 600 s budget with 5/10/20/30 s backoff, exact version plus a wheel or sdist, then a six-attempt `--no-cache-dir` install. Original scope: `fix(ci): robust publication wait for post-publish verification` — the 2026-10-09 failures were stale PyPI CDN nodes up to ~95–106 s after upload, not a fixed delay; poll the PyPI JSON API (`/pypi/<package>/<version>/json`) with a wall-clock budget until the version is listed before installing, rather than only waiting longer. Installing with `--no-cache-dir` is a secondary measure at most: pip already revalidates index pages rather than trusting a cached copy (separate from #240) | medium / S |
| P1 | pycubrid | `ci(release): verify the built distribution against the cookbook before publish` — **workflow:** `build` outputs `meta_sha256` (required: `RELEASE_NOTES.md`, `sbom.spdx.json`, `SHA256SUMS`) and `dist_artifact_id` (optional); `verify-candidate` + `require-candidate` (`if: !cancelled() && needs.build.result == 'success'`), with the candidate gate skipped only for `publish == true` and `tag_state == same` (section 7.3, step 5); `publish` needs `require-candidate`, sparse-checks out `scripts/verify_dist.py` next to `scripts/pypi_duplicate_guard.py`, and before the tag step verifies `dist/` against `needs.build.outputs.sha256` and `release-meta/` against `needs.build.outputs.meta_sha256` (exact file set, every digest), optionally downloading by artifact ID; `summary` `needs` gains `verify-candidate` and `require-candidate`, and `scripts/release_summary.py` reads those job names (pre-publish state and a candidate row); `publish`'s `if` gains `!cancelled()` and explicit results (section 7.3, step 5). **Scripts:** new `scripts/verify_dist.py` with `tests/test_verify_dist.py` (exact match passes; extra file, missing file, digest mismatch, subdirectory or symlink, empty/missing/non-JSON env value, non-hex digest or path-like key all fail); untagged `resume` in `scripts/release_detect.py` (section 7.3, step 3) with `tests/test_release_detect.py` cases: content commit is the first-parent commit where `__version__` became X.Y.Z, not the `main` head; ambiguity (X.Y.Z reached more than once on the first-parent history) is an error; PyPI absent (HTTP 404) proceeds, present (200) is an error, any other status, timeout or connection error fails closed; tag present keeps the old path (tag commit, `tag_state == same`); `__version__` at the `origin/main` head no longer X.Y.Z is an error; missing dated CHANGELOG section at the content commit is an error; `test_recovery_never_creates_a_new_version` keeps its assertion for `verify-only` only. **Existing exact assertions that change in `tests/test_release_workflows.py`:** `test_job_graph` (`jobs["publish"]["needs"] == ["detect", "consistency", "matrix", "build"]` gains `require-candidate`; `jobs["publish"]["if"] == "needs.detect.outputs.publish == 'true'"` (`tests/test_release_workflows.py:180`) becomes the `!cancelled() && …` condition of section 4 with an explicit `result == 'success'` for `consistency`, `matrix`, `build` and `require-candidate`; `jobs["summary"]["needs"]` gains `verify-candidate` and `require-candidate`; new `needs`/`if` asserts for both new jobs), `EXPECTED_PERMISSIONS` (gains `"verify-candidate": {"contents": "read"}` and `"require-candidate": {}`, and `set(jobs) == set(EXPECTED_PERMISSIONS)` then holds), `test_release_content_comes_from_the_detected_sha` (`publish`'s sparse checkout is no longer the single `scripts/pypi_duplicate_guard.py`), `test_publish_order_tag_draft_pypi_undraft` (the new check step precedes "Create the annotated tag"), `test_build_once_with_hashes_and_recoverable_artifacts` (asserts the `meta_sha256` output), `test_cookbook_is_verified_through_the_pinned_reusable_workflow` (today it checks only the first `smoke-test.yml@` line for `# main`), plus a new test that `publish` reads `needs.build.outputs.sha256` and `needs.build.outputs.meta_sha256`, and a same-SHA test: collect every `smoke-test.yml@` reference in the workflow file, assert exactly one distinct SHA, require each line to end with `# main`, and apply `COOKBOOK_SMOKE.match` to `verify-candidate["uses"]` as well as `verify-cookbook["uses"]`. `tests/test_workflow_timeouts.py` `EXTERNAL_REUSABLE_CALLERS` (a dict mapping `(file, job)` to the reusable workflow path) gains the `("publish-pypi.yml", "verify-candidate")` entry. Pin bump to the shared SHA (`ec0184a` or later; section 10). **Docs:** `RELEASING.md:120-121` ("PyPI cookbook verification checks the published version, not an unpublished local candidate artifact"), the rest of `RELEASING.md` and `docs/CI_POLICY.md` | high / M |
| P2 | pycubrid | `ci(release): optional cookbook_override_reason recovery input` (section 7.3, step 4) — blocked on the maintainer configuring required reviewers on the `pypi` environment, or documented as self-service | low / S |
| S1 | sqlalchemy-cubrid | same as P1, with the tests under `test/` (`test/test_verify_dist.py`, `test/test_release_detect.py`, `test/test_release_workflows.py`, and `test/test_workflow_timeouts.py`, whose `EXTERNAL_REUSABLE_CALLERS` already lists `("publish-pypi.yml", "verify-cookbook")` and gains the `("publish-pypi.yml", "verify-candidate")` entry); the same changed exact assertions, including `jobs["publish"]["if"]` at `test/test_release_workflows.py:177`, and the same same-SHA test; pin bump from `16f3a91` to the shared SHA; docs: the "Cookbook verification" section of `RELEASING.md` and `docs/CI_POLICY.md` | high / M |
| S2 | sqlalchemy-cubrid | same as P2 | low / S |
| M1 | cubrid-mcp-server | same as P1 for `release.yml` (`EXTERNAL_REUSABLE_CALLERS` gains the `("release.yml", "verify-candidate")` entry; the same changed exact assertions, including `jobs["publish"]["if"]` at `tests/test_release_workflows.py:154`, and the same same-SHA test; untagged-resume recovery command `gh workflow run release.yml -f action=resume -f version=X.Y.Z`); docs: the "Cookbook verification" section of `RELEASING.md`; bump the pin from `fe01e71` to the shared SHA | medium / M |
| M2 | cubrid-mcp-server | same as P2 | low / S |

## 12. Questions

Answered:

- **Do re-run attempts see artifacts uploaded by earlier attempts?** Yes.
  Artifacts belong to the workflow run, not to an attempt: a job re-run with
  `gh run rerun <id> --failed` downloads artifacts that jobs of earlier
  attempts uploaded. The cookbook already depends on this — its part uploads
  set `overwrite: true` (#188) precisely because a re-run job's upload would
  otherwise collide with the same-named artifact from the earlier attempt — and
  `publish`'s partial-upload recovery downloads `release-dist` from the
  attempt that ran `build`. For candidate mode this means a re-run of a failed
  candidate cell reuses the original `release-dist`, its artifact ID and the
  `build` hash outputs (`sha256`, `meta_sha256`). Because `build`'s uploads
  set no `overwrite`, recovery is always `gh run rerun <id> --failed`, never a
  full re-run of the run. The P1 dry-run should still exercise one forced
  failure and `--failed` re-run as a smoke check.
- **Can the calling job use `permissions: {}`?** No. A called workflow can only
  keep or reduce the permissions its caller grants, and `smoke-test.yml`
  declares top-level `permissions: contents: read` (its jobs check out this
  repository with `actions/checkout`). A caller granting `{}` makes GitHub
  reject the run at startup because the nested jobs request more than they are
  allowed. `contents: read` is the minimum; artifact upload/download does not
  need any `GITHUB_TOKEN` permission (it uses the runtime token).

Open:

- Whether the override (P2/S2/M2) is wanted at all; the design works without
  it, and it depends on the `pypi` environment reviewer decision in section
  7.3.
