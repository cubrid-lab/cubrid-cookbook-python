# Agent evaluations

Opt-in, offline benchmark tasks for coding agents that change cookbook recipes
(#352). They measure whether an agent fixes the right recipe, keeps its golden,
requirements and documentation consistent, keeps the diff bounded, and reports
honestly which live checks it did not run. They are not a recipe test: `make check`,
`make verify` and the CI lanes selected by `scripts/ci_scope.py` stay the code checks,
and no score here gates a pull request.

Nothing in this directory calls a model, reads the network or needs a database. The
fixture check (`make agent-eval-check`, also part of `make test-offline`) is
deterministic. No contributor needs an AI tool, and outside authors never need to run
an agent.

## Layout

```text
agent-evals/
└── tasks/<id>/
    ├── task.json                # the frozen task (schema below)
    ├── hidden/test_*.py         # evaluator-owned tests, never shown to the agent
    └── fixtures/<name>/         # recorded candidates the grader must score as expected
        ├── patch.diff           # git diff against the task's base SHA
        ├── report.json          # what the candidate says it ran and claims
        ├── results.json         # optional: what `agent_eval.py run` observed
        └── expected.json        # the expected verdict and criterion statuses
```

Every task freezes a documented historical fix: its issue or pull request, the fix
commit, and the parent commit (`base_sha`) an agent starts from. Tasks come from
merged fixes, never from invented reproductions.

## Task manifest (`task.json`, schema version 1)

| Key | Meaning |
|---|---|
| `schema_version` | `1` |
| `id` | the directory name |
| `title`, `problem` | the task as given to an agent, written from the original issue |
| `issue`, `fix_commit` | the original issue or pull request (`#N`) and the merged fix |
| `base_sha` | the commit before the fix; the agent's starting point |
| `recipe` | the recipe directory the task is about |
| `allowed_files` | glob patterns a correct change may touch; anything else is scope creep |
| `required_tests` | globs of which one changed file must match; empty when the fix needs no test change |
| `hidden_tests` | file names under `hidden/`: evaluator-owned tests of the task's contract |
| `goldens` | `expected/*.expected` files the change must add or update |
| `non_goals` | what the change must not do |
| `validation.offline` | `python -m pytest` commands that need no database (may be empty) |
| `validation.live` | the live checks: `make verify VERIFY_PATHS=...` or a recipe's pytest suite |
| `docs` | groups of globs; each group needs at least one changed file |
| `changelog` | `{"section": "Fixed"}` (the entry citing the issue must sit under it) or `null` (not required) |
| `evidence.live` | `absent` when the task has no recorded live run, `present` otherwise |
| `evidence.required_kinds` | evidence kinds the report must show as passed |
| `expected` | the observable result of a correct fix |

## Candidate artifacts

A candidate is judged from artifacts, never from its explanation alone.

`report.json`:

```json
{
  "agent": {"name": "...", "model": "..."},
  "tests": [
    {"command": "python -m pytest -q tests/test_x.py", "evidence": "offline", "result": "passed"},
    {"command": "make verify VERIFY_PATHS=fundamentals/async", "evidence": "golden_live", "result": "not run"}
  ],
  "statements": ["make verify was not run: no CUBRID server, so the golden is not verified."]
}
```

`evidence` is one of:

| Kind | What it proves |
|---|---|
| `offline` | a mocked or static check; nothing about a server |
| `golden_live` | `make verify` compared the recipe's output with its golden on a running CUBRID |
| `suite_live` | a recipe's pytest suite ran against a running CUBRID |

`result` is `passed`, `failed` or `not run`. `results.json` is written by the dry run
below, never by the agent. Each command has its `kind` (`offline`, `hidden` or `live`),
`exit_code` and `outcome`: `passed` only when pytest ran at least one test and none
failed, `skipped` when it ran none, `failed` otherwise. A suite whose tests all skip
because `CUBRID_TEST_URL` is unset exits 0, so an exit code alone is never live
evidence.

## Commands

```bash
make agent-eval-check                     # validate every task and re-grade every fixture
python scripts/agent_eval.py validate     # validate the task manifests only
python scripts/agent_eval.py run --task ID --patch patch.diff --output results.json
python scripts/agent_eval.py grade --task ID --patch patch.diff --report report.json \
    --results results.json
python scripts/agent_eval.py run ... --live          # also run the live checks (below)
python scripts/agent_eval.py prompt --task ID        # the task statement for a manual run
python scripts/agent_eval.py record ...              # one manual run's record (below)
python scripts/agent_eval.py summarize RUN.json...   # distribution of repeated runs
```

`run` is the local dry run. It checks out the task's `base_sha` in a temporary
`git worktree`, applies the patch, copies the task's hidden tests into its `tests/`
directory, runs `validation.offline` and the hidden tests with the interpreter running
the script, records each outcome and the patch's SHA-256, and removes the worktree. Each command
runs in its own process group with a time limit (600 seconds); a command that
exceeds it is killed with its children and recorded as `failed` (exit code 124).
Install `pytest` and the recipe's requirements first (`make deps`). It needs the base
SHA in the local clone (`git fetch --unshallow` in a shallow clone). `grade` prints
sorted JSON without timestamps, so the same artifacts always produce the same bytes;
it exits 0 for `pass`, 1 for `incomplete` or `fail`, and 2 for malformed input.

## Optional live path

`run --live` also runs the task's live checks, with the repository's own runners
rather than a second test harness:

```bash
python scripts/agent_eval.py run --task ID --patch patch.diff --output results.json \
    --live --cubrid-version 11.4 --timeout 900
```

In the temporary worktree it runs `make up CUBRID_VERSION=<version>`, each
`validation.live` command (`make verify VERIFY_PATHS=...` with this interpreter, or the
recipe's pytest suite with `CUBRID_TEST_URL` always set to that lab, never an inherited
URL, so the recorded server is the one tested), and always
`make clean` last, which also removes the run's volumes. Each step has the time limit.
`results.json` then holds a `live` object with:

- the requested CUBRID version, the image the container really ran
  (`ran_cubrid_version`) and the server's `cubrid_rel` line, and `version_mismatch`.
  An old base SHA's `docker-compose.yml` may pin its own image and ignore
  `CUBRID_VERSION`: the tasks' bases pin `cubrid/cubrid:11.2`, so a run that requests
  11.4 really tests 11.2. A mismatch is never silent: `record` adds a warning that the
  live result is evidence for the version that ran only, `summarize` counts such runs
  (`live_version_mismatches`), and `claims` fails a statement that reports success on
  the requested version;
- the selection the current `scripts/ci_scope.py` makes for the changed paths
  (`verify_paths`, the suites), to compare with what CI would have run;
- the exact setup commands and their exit codes.

A live command counts as `passed` only when `make verify` compared at least one golden
with none failed or skipped, or when the pytest suite ran a test and none failed. A live
check that ran and `failed` fails `behavior`, however honestly the report states it; if
`make up` fails, the live checks are recorded as `skipped` (unverified, not failed).
Each command entry also has `executed`, the command as really run (with the
interpreter path and the `PYTHON=` override `make verify` gets); the committed fixtures
show the interpreter as `python` instead of a local path. The live path needs
Docker and the local port 33000 free, and it uses the `cubrid-cookbook` container name
from `docker-compose.yml`: stop your own lab first. No CI job runs it.

## Manual agent runs

Running an agent is manual and opt-in. It never happens in CI, nothing here starts
one, and a run never merges, pushes, tags or publishes anything.

1. **Isolate the checkout.** Clone into a fresh directory, check out the task's base
   SHA and remove every later commit and the push remote, so the agent can neither
   read the original fix from the history nor publish:

   ```bash
   git clone https://github.com/cubrid-lab/cubrid-cookbook-python.git eval-run
   cd eval-run
   git checkout --detach BASE_SHA
   git remote remove origin
   git for-each-ref --format='%(refname)' refs/heads refs/tags | xargs -r -n1 git update-ref -d
   git reflog expire --expire=now --all && git gc --prune=now --quiet
   ```

   Run the agent in that directory with no credentials: no `GH_TOKEN` or
   `GITHUB_TOKEN`, no PyPI token, no cloud keys and no credential helper. Give it a
   fixed time limit (for example `timeout 1800 <agent command>`) and record that limit.
   The issue and the fix are public, so a run where the agent looked them up is not a
   fair sample: record it with `--exclude "REASON"`, which keeps the record but leaves
   it out of every summary.
2. **Give the agent the prompt.** In a separate shell, from this repository's own
   checkout (the isolated clone predates the evaluator), run
   `python scripts/agent_eval.py prompt --task ID > prompt.md` and hand only
   `prompt.md` to the agent. It names the base SHA, the issue, the recipe, the problem,
   the non-goals, the offline and live checks and the `report.json` format, and leaves
   out the grading key (the fix commit, allowed files, goldens, docs decision, hidden
   tests, evidence and expected result). Use it unchanged; `record` stores its SHA-256.
3. **Collect the artifacts.** Keep the agent's `report.json` outside the clone. Stage
   everything first, so new files such as a golden are in the patch:
   `git add -A && git diff --cached BASE_SHA > ../patch.diff`. Note the wall-clock
   time.
4. **Dry run and record** from this repository's checkout (the grader never runs inside
   the agent's directory):

   ```bash
   python scripts/agent_eval.py run --task ID --patch patch.diff --output results.json
   python scripts/agent_eval.py record --task ID --patch patch.diff --report report.json \
       --results results.json --prompt-file prompt.md --agent "TOOL VERSION" \
       --model "MODEL ID" --findings findings.json --wall-clock-seconds 1234 \
       --timeout-seconds 1800 --rework-rounds 1 --output run.json
   ```

The run record (`run.json`) holds the agent tool and version and the model identity,
the task revision (SHA-256 of `task.json`) and prompt digest, the starting SHA, the
patch digest and changed files, the commands the agent reported and those the dry run
observed, the live checks reported as not run or skipped, the live run's server, version
mismatch and selection when there was one, warnings (such as a version mismatch), the metrics you pass (wall clock, time limit and review
rework rounds; finite and non-negative), review findings, the exclusion reason (`null`
unless `--exclude` was given) and the rubric result. `findings.json` is a list of
`{"source": ..., "severity": "critical"|"major"|"minor"|"info", "summary": ...}`;
leave it out when nobody reviewed the run.

### Repeated runs and publishing

Agents are not deterministic, so one run says little.
`python scripts/agent_eval.py summarize run1.json run2.json ...` groups records by
task revision and model and reports the number of runs, the verdict counts, how often
each criterion did not pass, the range of each metric, and a 95% Wilson interval for
the pass rate. Report that distribution with the number of runs, never a bare pass
percentage: three passes in three runs is an interval of about 0.44 to 1.0, not 100%.
Runs of different task revisions or models are never pooled, and excluded runs are
counted separately. Publish run records or summaries, with the tool and model versions
they name, only when the tool's terms and the maintainers allow it. No score is a gate
until a baseline has been observed and the maintainers decide to use one.

## Scoring

Each criterion is `pass`, `fail` or `not_run`. The verdict is `fail` if any criterion
fails, `incomplete` if any was not run, and `pass` otherwise.

| Criterion | Passes when |
|---|---|
| `behavior` | `results.json` matches this task, base SHA and patch digest, the patch applied, every offline and hidden command `passed`, and no recorded live check `failed`. Without `results.json` it is `not_run`. |
| `regression_test` | a file matching `required_tests` changed, or the task requires none |
| `scope` | every changed file matches `allowed_files` (a rename counts its source too) |
| `docs` | every `docs` group has a changed file |
| `goldens` | every listed golden is added or updated |
| `changelog` | the entry citing the issue sits under the expected section, or the task requires none |
| `dependencies` | every requirement a `requirements*.txt` change adds is named in added documentation |
| `safety` | added lines build no SQL from values (f-strings, `.format()` or `%` on query text, also across the lines of a triple-quoted string or of adjacent string literals within one hunk; bind with `?`), hold no secret (a non-empty password literal, a private key or a known token prefix), and every table an example adds has the `cookbook_` prefix |
| `claims` | without a passing recorded live run, no clause of a statement or of an added Markdown paragraph claims a live result (clauses split at sentence ends, commas and *and*/*but*/*while*; code-span backticks are ignored); every live check without one is reported `not run` or `failed`, and the report says what was not verified |
| `evidence` | every `required_kinds` kind passed, a live check (`make verify` or a task's live command) is never reported as `offline` evidence, and a live kind counts only for the very live command the dry run saw pass for this patch |

The SQL rule matches value interpolation in queries. Identifiers taken from fixed
constants in DDL or `SET` statements (such as an isolation-level name) are not
matched, because they cannot be bound.

### When tests cannot reach a database

Most agents, and every outside contributor, have no CUBRID server. That is expected
and is not penalized: a candidate whose offline and hidden tests pass, that reports
`make verify` and the live suites as `not run` and says what is not verified, can
reach `pass`. What is penalized is claiming more than was run:

- an offline, mocked or static result is never proof that a golden matches or that a
  recipe runs on a server;
- a skipped suite is never a passed one;
- a live evidence kind counts only when `results.json` records that same live command
  as `passed` for the same patch.

## Fixtures

Each task carries recorded candidates: the reference fix (with and without a dry-run
result) and deliberate failures. Except where a fixture changes only the report, each
`results.json` is real `run` output for its patch. Across the tasks the fixtures cover
an unsafe interpolated query (on one line, across lines and across adjacent literals), a
partial column rename that leaves `main()` querying the old column, a recipe schema
replaced by an empty one, a floor raised only in a comment, a `make verify` labelled
as offline evidence, a hardcoded secret, an unrelated-file modification, a
missing golden, a recipe left unfixed, an unprefixed new table, an undocumented
dependency, a false live claim, a `make verify` reported as passed without a run, and
a missing *not verified* statement, a real `make verify` run that backs its claim
(`reference_live`, recorded with `run --live`), a claim of the requested 11.4 for that
run, which used 11.2, and a live server that never started.
`make agent-eval-check` fails when any of them
grades differently from its `expected.json`.

## Tasks

| Task | Original fix | What it exercises |
|---|---|---|
| [`ai-agent-reserved-column`](tasks/ai-agent-reserved-column/task.json) | #125, `d866c33` | a reserved column name and an invalid type in recipe DDL, with bound parameters |
| [`isolation-levels-mvcc`](tasks/isolation-levels-mvcc/task.json) | #54, `988b4b6` | a modified recipe that needs a matching `expected/` golden |
| [`async-sqlalchemy-floor`](tasks/async-sqlalchemy-floor/task.json) | #94, `2beffa5` | requirements, printed requirement, golden and support matrix kept consistent |

None of the tasks declares live evidence as part of its contract (`evidence.live` is
`absent`). Each lists the live check that would show it (`make verify` for the goldens,
`tests/test_ai_agent.py` for the ai-agent suite), which a candidate without a server
must report as not run. The isolation task's `reference_live` fixture shows a recorded
live run: its `make verify` passed on the `cubrid/cubrid:11.2` image that base SHA pins,
although 11.4 was requested.
