"""Offline tests of the agent-evals task format and grader (#352)."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import agent_eval as ae  # noqa: E402

TASK_IDS = sorted(p.parent.name for p in (ae.EVALS / "tasks").glob("*/task.json"))
AI = "ai-agent-reserved-column"
ISO = "isolation-levels-mvcc"
ASYNC = "async-sqlalchemy-floor"


def _fixture(task_id: str, name: str) -> tuple[str, Any, Any]:
    folder = ae.EVALS / "tasks" / task_id / "fixtures" / name
    results = folder / "results.json"
    return (
        (folder / "patch.diff").read_text(encoding="utf-8"),
        ae.load_json(folder / "report.json"),
        ae.load_json(results) if results.exists() else None,
    )


def _grade(task_id: str, name: str) -> dict[str, Any]:
    return ae.grade(ae.load_task(task_id), *_fixture(task_id, name))


def _statuses(result: dict[str, Any]) -> dict[str, str]:
    return {name: c["status"] for name, c in result["criteria"].items()}


def _patch(path: str, *added: str, context: tuple[str, ...] = ()) -> str:
    lines = [f"diff --git a/{path} b/{path}", f"--- a/{path}", f"+++ b/{path}", "@@ -1 +1 @@"]
    lines += [f" {c}" for c in context] + [f"+{a}" for a in added]
    return "\n".join(lines) + "\n"


def test_every_recorded_fixture_grades_as_expected() -> None:
    assert ae.check() == []


def test_three_grounded_tasks_cover_the_issue_scenarios() -> None:
    assert TASK_IDS == [AI, ASYNC, ISO]
    for task_id in TASK_IDS:
        task = ae.load_task(task_id)
        assert task["issue"].startswith("#") and len(task["fix_commit"]) == 40
        assert task["evidence"]["live"] == "absent" and task["validation"]["live"]
    assert ae.load_task(ISO)["goldens"]
    assert ae.load_task(ASYNC)["docs"] == [["SUPPORT_MATRIX.md"]]


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_each_reference_passes_every_criterion(task_id: str) -> None:
    result = _grade(task_id, "reference")
    assert result["verdict"] == "pass", result
    assert set(_statuses(result).values()) == {"pass"}


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_grading_is_byte_for_byte_deterministic(task_id: str) -> None:
    assert ae.dump(_grade(task_id, "reference")) == ae.dump(_grade(task_id, "reference"))


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_missing_results_is_incomplete_never_pass(task_id: str) -> None:
    result = _grade(task_id, "reference_without_results")
    assert result["verdict"] == "incomplete"
    assert _statuses(result)["behavior"] == "not_run"


@pytest.mark.parametrize(
    ("task_id", "fixture", "criterion"),
    [
        (AI, "unsafe_query", "safety"),
        (AI, "unsafe_multiline_query", "safety"),
        (AI, "partial_rename", "behavior"),
        (AI, "missing_schema", "behavior"),
        (AI, "unsafe_adjacent_strings", "safety"),
        (ASYNC, "commented_requirement", "behavior"),
        (ISO, "live_check_labelled_offline", "evidence"),
        (ISO, "live_check_failed", "behavior"),
        (AI, "hardcoded_secret", "safety"),
        (AI, "unrelated_file", "scope"),
        (AI, "false_live_claim", "claims"),
        (ISO, "missing_golden", "goldens"),
        (ISO, "wrong_behavior", "behavior"),
        (ISO, "unprefixed_table", "safety"),
        (ISO, "verify_reported_passed", "evidence"),
        (ASYNC, "undocumented_dependency", "dependencies"),
        (ASYNC, "wrong_behavior", "behavior"),
        (ASYNC, "missing_not_verified", "claims"),
    ],
)
def test_each_deliberate_failure_fails_its_criterion(
    task_id: str, fixture: str, criterion: str
) -> None:
    result = _grade(task_id, fixture)
    assert result["verdict"] == "fail"
    assert _statuses(result)[criterion] == "fail"


def test_a_skipped_live_suite_backs_no_claim() -> None:
    task = ae.load_task(AI)
    patch, report, results = _fixture(AI, "reference")
    live = task["validation"]["live"][0]
    report = copy.deepcopy(report)
    report["tests"][-1]["result"] = "passed"
    report["statements"] = ["The ai-agent suite passed against a live CUBRID."]
    skipped = copy.deepcopy(results)
    skipped["commands"].append(
        {"command": live, "exit_code": 0, "kind": "live", "outcome": "skipped"}
    )
    statuses = _statuses(ae.grade(task, patch, report, skipped))
    assert statuses["claims"] == statuses["evidence"] == "fail"
    passed = copy.deepcopy(skipped)
    passed["commands"][-1]["outcome"] = "passed"
    statuses = _statuses(ae.grade(task, patch, report, passed))
    assert statuses["claims"] == statuses["evidence"] == "pass"
    passed["patch_sha256"] = "0" * 64
    assert _statuses(ae.grade(task, patch, report, passed))["evidence"] == "fail"


@pytest.mark.parametrize(
    ("line", "flagged"),
    [
        ('cur.execute(f"SELECT * FROM cookbook_t WHERE id = {item_id}")', True),
        ("cur.execute(f'INSERT INTO cookbook_t VALUES ({a}, {b})')", True),
        ('cur.execute("DELETE FROM cookbook_t WHERE id = %s" % item_id)', True),
        ('cur.execute("UPDATE cookbook_t SET val = {}".format(val))', True),
        ('cur.execute("SELECT * FROM cookbook_t WHERE id = ?", [item_id])', False),
        ('cur.execute(f"SET TRANSACTION ISOLATION LEVEL {name}")', False),
        ('cur.execute(f"DROP TABLE IF EXISTS {TABLE}")', False),
    ],
)
def test_sql_interpolation_rule(line: str, flagged: bool) -> None:
    assert bool(ae.SQL_INTERPOLATION.search(line)) is flagged


@pytest.mark.parametrize(
    ("line", "flagged"),
    [
        ('"password": "s3cret",', True),
        ("password='hunter2'", True),
        ("token = 'ghp_" + "a" * 36 + "'", True),
        ('"password": os.environ.get("CUBRID_PASSWORD", ""),', False),
        ('password=""', False),
    ],
)
def test_secret_rule(line: str, flagged: bool) -> None:
    assert bool(ae.SECRET.search(line)) is flagged


def test_multiline_sql_is_checked_whole_within_a_hunk() -> None:
    def hunk(*lines: str) -> dict[str, list[tuple[str, str]]]:
        return {"fundamentals/x/01_x.py": [("@", "@@")] + [(line[0], line[1:]) for line in lines]}

    unsafe = hunk(
        ' cur.execute(f"""', "+    SELECT * FROM cookbook_t", "+    WHERE id = {item_id}", ' """)'
    )
    assert ae._safety({}, unsafe)["status"] == "fail"
    formatted = hunk('+cur.execute("""', "+DELETE FROM cookbook_t WHERE id = {}", '+""".format(x))')
    assert ae._safety({}, formatted)["status"] == "fail"
    bound = hunk('+cur.execute("""', "+SELECT * FROM cookbook_t WHERE id = ?", '+""", [x])')
    assert ae._safety({}, bound)["status"] == "pass"
    # An unchanged unsafe query next to an added line that is not part of it is not new.
    kept = hunk(' q = f"""SELECT * FROM t WHERE id = {i}"""', "+print('done')")
    assert ae._safety({}, kept)["status"] == "pass"
    split = {
        "a.py": [
            ("@", "@@"),
            ("+", 'q = f"""SELECT * FROM t'),
            ("@", "@@"),
            ("+", 'WHERE id = {i}"""'),
        ]
    }
    assert ae._safety({}, split)["status"] == "pass"


@pytest.mark.parametrize(
    ("lines", "flagged"),
    [
        ([" cur.execute(", '+  "INSERT INTO t (a) VALUES ("', '+  f"{a})",'], True),
        (["+cur.execute(", '+  "SELECT * FROM t "', '+  f"WHERE id = {i}")'], True),
        (["+cur.execute(", '+  "SELECT * FROM t "', '+  "WHERE id = ?", [i])'], False),
        ([' q = "SELECT 1"', '+print(f"{x}")'], False),
        ([' cur.execute("SELECT 1 "', ' f"{x}")', "+print('done')"], False),
    ],
)
def test_adjacent_string_literals_are_joined(lines: list[str], flagged: bool) -> None:
    hunk = [(line[0], line[1:]) for line in lines]
    assert bool(ae._adjacent_sql("a.py", hunk)) is flagged


def test_safety_checks_tables_only_in_example_files() -> None:
    bad = ae._safety({"fundamentals/x/01_x.py": ['DDL = "CREATE TABLE scratch (id INT)"']}, {})
    assert bad["status"] == "fail"
    orm = ae._safety({"templates/flask/models.py": ['    __tablename__ = "users"']}, {})
    assert orm["status"] == "fail"
    good = ae._safety({"fundamentals/x/01_x.py": ['DDL = "CREATE TABLE cookbook_x (id INT)"']}, {})
    assert good["status"] == "pass"
    fixture = ae._safety(
        {"fundamentals/x/tests/test_x.py": ['"CREATE TABLE scratch (id INT)"']}, {}
    )
    assert fixture["status"] == "pass"


def test_dependencies_need_a_mention_in_added_documentation() -> None:
    req = _patch("fundamentals/x/requirements.txt", "httpx>=0.27", "# a comment", "-r ../base.txt")
    assert ae._dependencies(ae._hunks(req))["status"] == "fail"
    documented = req + _patch("fundamentals/x/README.md", "Install httpx for the client.")
    assert ae._dependencies(ae._hunks(documented))["status"] == "pass"
    assert ae._dependencies(ae._hunks(_patch("README.md", "text")))["status"] == "pass"


def test_wrapped_and_mixed_claims_are_caught() -> None:
    task = ae.load_task(ISO)
    patch, report, results = _fixture(ISO, "reference")
    for added in (["make verify passed."], ["make verify", "passed."]):
        result = ae.grade(task, patch + _patch("README.md", *added), report, results)
        assert _statuses(result)["claims"] == "fail", added
    for statement in (
        "Tested against CUBRID 11.4. The suite was not run.",
        "make verify passed and the live suite was not run.",
        "`make verify` passed.",
    ):
        mixed = copy.deepcopy(report)
        mixed["statements"] = [statement, report["statements"][-1]]
        assert _statuses(ae.grade(task, patch, mixed, results))["claims"] == "fail", statement
    spanned = patch + _patch("README.md", "`make verify` passed.")
    assert _statuses(ae.grade(task, spanned, report, results))["claims"] == "fail"


def test_changelog_is_optional_unless_the_task_names_a_section() -> None:
    task = ae.load_task(ASYNC)
    assert ae._changelog(task, "")["status"] == "pass"
    sectioned = dict(task, changelog={"section": "Fixed"})
    entry = "- **Async floor (#94)**"
    good = _patch("CHANGELOG.md", entry, context=("### Fixed", ""))
    assert ae._changelog(sectioned, good)["status"] == "pass"
    wrong = _patch("CHANGELOG.md", entry, context=("### Added", ""))
    assert ae._changelog(sectioned, wrong)["status"] == "fail"
    assert ae._changelog(sectioned, _patch("CHANGELOG.md", "- uncited"))["status"] == "fail"


def test_validate_task_reports_each_problem() -> None:
    task = ae.load_task(AI)
    assert ae.validate_task(task) == []
    assert ae.validate_task([]) == ["task: must be a JSON object"]
    broken = dict(task, base_sha="07033f3", issue="125", recipe="", extra=1)
    broken["goldens"] = ["fundamentals/x/out.txt"]
    broken["hidden_tests"] = []
    broken["validation"] = {"offline": ["pytest x"], "live": ["docker compose up"]}
    assert "validation.live" in " ".join(ae.validate_task(dict(task, validation={"offline": []})))
    assert "validation.offline" in " ".join(ae.validate_task(dict(task, validation={"live": []})))
    for docs in ([[None]], [[""]], [[]], ["README.md"]):
        assert "docs must be" in " ".join(ae.validate_task(dict(task, docs=docs))), docs
    broken["evidence"] = {"live": "maybe", "required_kinds": ["smoke"]}
    del broken["expected"]
    errors = " ".join(ae.validate_task(broken))
    for fragment in (
        "missing keys ['expected']",
        "unknown keys ['extra']",
        "base_sha must be a full",
        "issue must look like",
        "recipe must name",
        "goldens must list",
        "hidden_tests must be",
        "validation.offline",
        "validation.live",
        "evidence.live",
        "evidence.required_kinds",
    ):
        assert fragment in errors


@pytest.mark.parametrize(
    "report",
    [[], {"tests": "x"}, {"tests": [], "statements": [1]}, {"tests": [None]}],
)
def test_malformed_report_raises(report: Any) -> None:
    with pytest.raises(ae.EvalError):
        ae.grade(ae.load_task(AI), "", report, None)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: [],
        lambda r: {**r, "applied": "yes"},
        lambda r: {**r, "commands": [{**r["commands"][0], "outcome": "ok"}]},
        lambda r: {**r, "commands": [{**r["commands"][0], "kind": "smoke"}]},
    ],
)
def test_malformed_results_raise(change: Any) -> None:
    patch, report, results = _fixture(AI, "reference")
    with pytest.raises(ae.EvalError):
        ae.grade(ae.load_task(AI), patch, report, change(results))


def test_check_reports_a_fixture_that_grades_differently(tmp_path: Path) -> None:
    source = ae.EVALS / "tasks" / AI
    task_dir = tmp_path / "agent-evals" / "tasks" / AI
    (task_dir / "hidden").mkdir(parents=True)
    (task_dir / "task.json").write_bytes((source / "task.json").read_bytes())
    for hidden in (source / "hidden").iterdir():
        (task_dir / "hidden" / hidden.name).write_bytes(hidden.read_bytes())
    fixture = task_dir / "fixtures" / "flipped"
    fixture.mkdir(parents=True)
    for name in ("patch.diff", "report.json", "results.json"):
        (fixture / name).write_bytes((source / "fixtures" / "reference" / name).read_bytes())
    (fixture / "expected.json").write_text('{"criteria": {}, "verdict": "fail"}', "utf-8")
    problems = ae.check(tmp_path / "agent-evals")
    assert len(problems) == 1 and problems[0].startswith(f"{AI}/flipped: graded")
    (task_dir / "hidden" / "test_hidden_ai_agent_schema.py").unlink()
    assert "hidden test" in ae.check(tmp_path / "agent-evals")[0]
    assert ae.check(tmp_path / "none") == [f"no tasks under {tmp_path / 'none' / 'tasks'}"]


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return done.stdout.decode().strip()


def test_run_copies_hidden_tests_and_records_outcomes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "value.txt").write_text("old\n", encoding="utf-8")
    (repo / "tests" / "test_offline.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "b")
    task = dict(ae.load_task(AI), base_sha=_git(repo, "rev-parse", "HEAD"))
    task["validation"] = {"offline": ["python -m pytest -q tests/test_offline.py"], "live": []}
    patch = "\n".join(
        ["diff --git a/value.txt b/value.txt", "--- a/value.txt", "+++ b/value.txt"]
        + ["@@ -1 +1 @@", "-old", "+new", ""]
    )
    result = ae.run(task, patch, repo=repo)
    assert result["applied"] is True
    assert result["patch_sha256"] == hashlib.sha256(patch.encode()).hexdigest()
    outcomes = {c["kind"]: c["outcome"] for c in result["commands"]}
    # The hidden ai-agent test finds no recipe in this throwaway repository.
    assert outcomes == {"offline": "passed", "hidden": "failed"}
    assert ae.run(task, "not a patch\n", repo=repo)["applied"] is False
    assert "agent-eval-" not in _git(repo, "worktree", "list")


def test_a_hung_command_is_killed_and_recorded_as_failed(tmp_path: Path) -> None:
    script = "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); time.sleep(60)"
    started = time.monotonic()
    code, output = ae._bounded([sys.executable, "-c", script], tmp_path, 1.0)
    assert (code, output) == (124, "")
    assert time.monotonic() - started < 30
    assert ae.pytest_outcome(code, output) == "failed"


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ref = ae.EVALS / "tasks" / AI / "fixtures" / "reference"
    args = ["grade", "--task", AI, "--patch", str(ref / "patch.diff")]
    args += ["--report", str(ref / "report.json")]
    assert ae.main([*args, "--results", str(ref / "results.json")]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "pass"
    assert ae.main(args) == 1
    assert ae.main([*args[:-1], str(tmp_path / "missing.json")]) == 2
    assert ae.main(["validate"]) == 0
    assert ae.main(["check"]) == 0
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "agent_eval.py"), "validate"],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr


def test_a_real_live_run_backs_its_claim_and_records_the_server() -> None:
    result = _grade(ISO, "reference_live")
    assert result["verdict"] == "pass"
    _, _, results = _fixture(ISO, "reference_live")
    live = results["live"]
    assert live["requested_cubrid_version"] == "11.4"
    assert live["image"] == "cubrid/cubrid:11.2" and live["server"].startswith("CUBRID 11.2")
    # The base SHA's docker-compose.yml pins 11.2: the mismatch is recorded, not hidden.
    assert (live["ran_cubrid_version"], live["version_mismatch"]) == ("11.2", True)
    claims = _grade(ISO, "claims_requested_version")
    assert (
        _statuses(claims)["claims"] == "fail"
        and "cubrid/cubrid:11.2" in (claims["criteria"]["claims"]["detail"])
    )
    assert live["selection"]["verify_paths"] == "fundamentals/isolation-levels"
    assert [s["command"] for s in live["setup"]] == ["make up CUBRID_VERSION=11.4", "make clean"]
    unavailable = _grade(ISO, "live_server_unavailable")
    assert _statuses(unavailable)["evidence"] == "fail"


@pytest.mark.parametrize(
    ("exit_code", "output", "outcome"),
    [
        (0, "  ✓ PASS a.py\nResults: 1 passed, 0 failed, 0 skipped (0 mismatch)\n", "passed"),
        (2, "Results: 1 passed, 1 failed, 0 skipped (1 mismatch)\n", "failed"),
        (2, "Results: 0 passed, 0 failed, 1 skipped (0 mismatch)\n", "skipped"),
        (2, "ERROR: No golden targets found\n", "failed"),
        (0, "", "skipped"),
    ],
)
def test_verify_outcome(exit_code: int, output: str, outcome: str) -> None:
    assert ae.verify_outcome(exit_code, output) == outcome


def test_live_path_uses_make_and_always_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], float, dict[str, str] | None]] = []

    def fake_bounded(argv, cwd, timeout, env=None):  # noqa: ANN001, ANN202
        calls.append((list(argv), timeout, env))
        if argv[:2] == ["docker", "inspect"]:
            return 0, "cubrid/cubrid:11.4\n"
        if argv[:2] == ["docker", "exec"]:
            return 0, "\nCUBRID 11.4 (11.4.0.1778) (64bit release build)\n"
        if argv[:2] == ["make", "verify"]:
            raise RuntimeError("verify crashed")
        return 0, ""

    monkeypatch.setattr(ae, "_bounded", fake_bounded)
    monkeypatch.setattr(
        ae.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "tier=pr\nverify_paths=x\n", ""),
    )
    monkeypatch.setenv("CUBRID_TEST_URL", "cubrid://dba:@elsewhere:33000/otherdb")
    task = ae.load_task(ISO)
    commands: list[dict[str, Any]] = []
    with pytest.raises(RuntimeError):
        ae._live(task, "", tmp_path, commands, "11.4", 5)
    argvs = [argv for argv, _, _ in calls]
    assert argvs[0] == ["make", "up", "CUBRID_VERSION=11.4"]
    assert argvs[1][:2] == ["docker", "inspect"] and argvs[2][:2] == ["docker", "exec"]
    assert argvs[3][:3] == ["make", "verify", "VERIFY_PATHS=fundamentals/isolation-levels"]
    assert argvs[3][-1] == f"PYTHON={sys.executable}"
    assert argvs[-1] == ["make", "clean"]
    # Every step, the probes included, is bounded; the suite URL is pinned to the lab.
    assert all(timeout <= 5 for _, timeout, _ in calls)
    assert all(env["CUBRID_TEST_URL"] == ae.LAB_URL for _, _, env in calls if env)

    calls.clear()

    def no_server(argv, cwd, timeout, env=None):  # noqa: ANN001, ANN202
        calls.append((list(argv), timeout, env))
        return (124, "") if argv[0] == "docker" else (2, "")

    monkeypatch.setattr(ae, "_bounded", no_server)
    info = ae._live(task, "", tmp_path, commands, "11.2", 5)
    assert commands[-1]["outcome"] == "skipped" and calls[-1][0] == ["make", "clean"]
    assert (info["image"], info["server"], info["version_mismatch"]) == (None, None, None)
    assert info["selection"] == {"tier": "pr", "verify_paths": "x"}

    monkeypatch.setattr(ae, "_bounded", lambda argv, cwd, timeout, env=None: (0, ""))
    commands.clear()
    ae._live(task, "", tmp_path, commands, "11.4", 5)
    assert commands[-1]["executed"] == (
        f"make verify VERIFY_PATHS=fundamentals/isolation-levels PYTHON={sys.executable}"
    )


def test_live_cleanup_uses_docker_clean_when_the_worktree_has_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #437: make clean no longer removes volumes; base SHAs before it have no
    # docker-clean target, and there make clean still runs `down -v`.
    calls: list[list[str]] = []
    monkeypatch.setattr(
        ae, "_bounded", lambda argv, cwd, timeout, env=None: calls.append(list(argv)) or (0, "")
    )
    monkeypatch.setattr(
        ae.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "", "")
    )
    task = ae.load_task(ISO)
    (tmp_path / "Makefile").write_text("clean:\n\trm -rf .ruff_cache\n", encoding="utf-8")
    info = ae._live(task, "", tmp_path, [], "11.4", 5)
    assert calls[-1] == ["make", "clean"] and info["setup"][-1]["command"] == "make clean"
    (tmp_path / "Makefile").write_text(
        "clean:\n\trm -rf .ruff_cache\ndocker-clean: ## x\n\tdocker compose down -v\n",
        encoding="utf-8",
    )
    info = ae._live(task, "", tmp_path, [], "11.4", 5)
    assert calls[-1] == ["make", "docker-clean"]
    assert info["setup"][-1]["command"] == "make docker-clean"


def test_an_honestly_reported_live_failure_still_fails_behavior() -> None:
    result = _grade(ISO, "live_check_failed")
    statuses = _statuses(result)
    assert (statuses["behavior"], statuses["claims"], statuses["evidence"]) == (
        "fail",
        "pass",
        "pass",
    )
    assert "live check failed" in result["criteria"]["behavior"]["detail"]
    # A skipped live check stays unverified, not failed.
    assert _statuses(_grade(ISO, "live_server_unavailable"))["behavior"] == "pass"


def test_disclosing_the_requested_version_is_not_a_claim_of_it() -> None:
    task = ae.load_task(ISO)
    patch, report, results = _fixture(ISO, "claims_requested_version")
    for statement, status in (
        ("make verify passed on CUBRID 11.2 (11.4 was requested).", "pass"),
        ("make verify passed on CUBRID 11.4.", "fail"),
        ("CUBRID 11.4 was requested but not verified.", "pass"),
    ):
        honest = copy.deepcopy(report)
        honest["statements"] = [statement]
        assert _statuses(ae.grade(task, patch, honest, results))["claims"] == status, statement


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_prompt_leaves_out_the_grading_key(task_id: str) -> None:
    task = ae.load_task(task_id)
    text = ae.prompt(task)
    assert text == ae.prompt(task)
    for shown in (task["base_sha"], task["problem"], task["issue"], task["recipe"]):
        assert shown in text
    for hidden in (task["fix_commit"], task["fix_commit"][:7], task["expected"]):
        assert hidden not in text
    assert "allowed" not in text.lower() and "hidden" not in text.lower()
    for word in (*ae.EVIDENCE_KINDS, *ae.RESULTS):
        assert word in text


def _record(**overrides: Any) -> dict[str, Any]:
    task = ae.load_task(ISO)
    patch, report, results = _fixture(ISO, "reference_live")
    args: dict[str, Any] = {
        "task": task,
        "revision": ae.task_revision(ISO),
        "prompt_text": ae.prompt(task),
        "agent": {"name": "tool 1.0", "model": "model-a"},
        "patch": patch,
        "report": report,
        "results": results,
        "metrics": {"wall_clock_seconds": 60.0, "timeout_seconds": 1800, "rework_rounds": 1},
        "findings": [{"source": "maintainer", "severity": "minor", "summary": "wording"}],
    }
    args.update(overrides)
    return ae.record(**args)


def test_record_holds_identity_live_run_metrics_and_rubric() -> None:
    entry = _record()
    assert entry["agent"] == {"name": "tool 1.0", "model": "model-a"}
    assert entry["start_sha"] == ae.load_task(ISO)["base_sha"]
    assert entry["live_run"]["image"] == "cubrid/cubrid:11.2"
    assert entry["warnings"] == [
        "requested CUBRID 11.4 but the container ran cubrid/cubrid:11.2: "
        "the live result is evidence for 11.2 only"
    ]
    assert entry["metrics"] == {
        "rework_rounds": 1,
        "timeout_seconds": 1800,
        "wall_clock_seconds": 60.0,
    }
    assert entry["skipped_live_checks"] == [] and entry["rubric"]["verdict"] == "pass"
    assert ae.dump(entry) == ae.dump(_record())
    patch, report, _ = _fixture(ISO, "reference")
    offline = _record(patch=patch, report=report, results=None)
    assert offline["skipped_live_checks"] == ae.load_task(ISO)["validation"]["live"]
    assert offline["live_run"] is None and offline["rubric"]["verdict"] == "incomplete"
    assert offline["warnings"] == []
    _, unavailable_report, unavailable = _fixture(ISO, "live_server_unavailable")
    down = _record(report=unavailable_report, results=unavailable)
    assert down["warnings"] == ["the live run's CUBRID image is unknown (the server did not start)"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"agent": {"name": "tool"}},
        {"findings": [{"source": "x", "severity": "blocker", "summary": "y"}]},
        {"metrics": {"wall_clock_seconds": float("nan")}},
        {"metrics": {"tokens": 5}},
        {"metrics": {"rework_rounds": -1}},
        {"exclude": " "},
    ],
)
def test_record_rejects_bad_identity_findings_metrics_and_exclusion(overrides: Any) -> None:
    with pytest.raises(ae.EvalError):
        _record(**overrides)


def test_summarize_reports_counts_intervals_and_exclusions() -> None:
    passing = _record()
    failing = copy.deepcopy(passing)
    failing["rubric"]["verdict"] = "fail"
    failing["rubric"]["criteria"]["goldens"]["status"] = "fail"
    failing["metrics"] = {"wall_clock_seconds": 120.0, "rework_rounds": 3}
    other = copy.deepcopy(passing)
    other["agent"]["model"] = "model-b"
    excluded = _record(exclude="the agent read the public fix")
    summary = ae.summarize([passing, failing, other, excluded])
    first, second = summary["groups"]
    assert (first["model"], first["runs"], first["excluded"]) == ("model-a", 2, 1)
    assert first["live_version_mismatches"] == 2
    assert first["verdicts"] == {"pass": 1, "incomplete": 0, "fail": 1}
    assert first["criteria_not_passed"] == {"goldens": 1}
    assert first["pass_interval_95"] == ae.wilson(1, 2)
    assert first["metrics"]["rework_rounds"] == {"min": 1, "median": 2.0, "max": 3}
    assert (second["model"], second["runs"]) == ("model-b", 1)
    assert ae.wilson(3, 3) == [0.438, 1.0] and ae.wilson(0, 0) == [0.0, 1.0]
    for broken in (
        {"schema_version": 1},
        dict(passing, agent={"model": []}),
        dict(passing, metrics={"wall_clock_seconds": float("inf")}),
        dict(passing, rubric={"verdict": "pass", "criteria": []}),
        dict(passing, live_run=["image"]),
        dict(passing, live_run="cubrid/cubrid:11.2"),
    ):
        with pytest.raises(ae.EvalError):
            ae.summarize([broken])


def test_cli_prompt_record_summarize(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert ae.main(["prompt", "--task", ISO]) == 0
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text(capsys.readouterr().out, encoding="utf-8")
    ref = ae.EVALS / "tasks" / ISO / "fixtures" / "reference_live"
    out = tmp_path / "run.json"
    args = ["record", "--task", ISO, "--patch", str(ref / "patch.diff")]
    args += ["--report", str(ref / "report.json"), "--results", str(ref / "results.json")]
    args += ["--prompt-file", str(prompt_file), "--agent", "tool 1.0", "--model", "m"]
    args += ["--wall-clock-seconds", "12.5", "--timeout-seconds", "1800", "--rework-rounds", "0"]
    assert ae.main([*args, "--output", str(out)]) == 0
    entry = json.loads(out.read_text(encoding="utf-8"))
    assert entry["prompt_sha256"] == hashlib.sha256(prompt_file.read_bytes()).hexdigest()
    assert entry["metrics"] == {
        "rework_rounds": 0,
        "timeout_seconds": 1800.0,
        "wall_clock_seconds": 12.5,
    }
    capsys.readouterr()
    assert ae.main(["summarize", str(out), str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["groups"][0]["runs"] == 2
    bad = tmp_path / "findings.json"
    bad.write_text("{}", encoding="utf-8")
    assert ae.main([*args, "--findings", str(bad), "--output", str(out)]) == 2
