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
