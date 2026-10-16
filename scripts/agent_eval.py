#!/usr/bin/env python3
"""Offline, deterministic grader for the opt-in agent evaluations in ``agent-evals/`` (#352).

An evaluation task (``agent-evals/tasks/<id>/task.json``) freezes a documented
historical recipe fix: the base SHA before it, the recipe, the problem, the files a
correct change may touch, the goldens and documentation it must keep in step, the
evaluator-owned (hidden) tests that check its contract, and the live checks it has
no recorded evidence for.

A candidate is three artifacts, never the agent's explanation alone:

* ``patch.diff``: the change, as ``git diff`` output against the base SHA;
* ``report.json``: what the agent says it ran and claims (see the README);
* ``results.json`` (optional): what ``scripts/agent_eval.py run`` observed when it
  applied the patch at the base SHA and ran the task's offline and hidden tests.

``grade`` scores the candidate. Every criterion is ``pass``, ``fail`` or
``not_run``; without ``results.json`` the behavior criterion is ``not_run``, so
the verdict is at best ``incomplete``. The output is sorted JSON with no
timestamps: the same artifacts always produce the same bytes. ``check`` grades
every recorded fixture and compares it with its ``expected.json``. Nothing here
calls a model, reads the network or needs a database.

Usage::

    python scripts/agent_eval.py validate
    python scripts/agent_eval.py check
    python scripts/agent_eval.py run --task ID --patch P --output J
    python scripts/agent_eval.py grade --task ID --patch P --report R [--results J]

``run`` is the local dry run: it checks out the task's base SHA in a temporary
``git worktree``, applies the patch, copies the hidden tests into its ``tests/``
directory, runs the offline and hidden commands, records each pytest outcome and
removes the worktree. It needs the base SHA in the local clone.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "agent-evals"
SCHEMA_VERSION = 1

# Evidence kinds an agent may report. ``offline`` is a mocked or static test; only
# ``golden_live`` (``make verify`` against a running CUBRID) and ``suite_live`` (a
# recipe's pytest suite against a running CUBRID) say anything about a server.
EVIDENCE_KINDS = ("offline", "golden_live", "suite_live")
LIVE_KINDS = frozenset({"golden_live", "suite_live"})
RESULTS = ("passed", "failed", "not run")

TASK_KEYS = {
    "schema_version",
    "id",
    "title",
    "issue",
    "fix_commit",
    "base_sha",
    "recipe",
    "problem",
    "allowed_files",
    "required_tests",
    "hidden_tests",
    "goldens",
    "non_goals",
    "validation",
    "docs",
    "changelog",
    "evidence",
    "expected",
}
PYTEST = "python -m pytest "
# Live commands are the repository's own runners: ``make verify`` for goldens and
# a recipe's pytest suite. The grader never runs them; ``run`` does not either.
LIVE_PREFIXES = ("make verify ", PYTEST)
COMMAND_KINDS = ("offline", "hidden", "live")
OUTCOMES = ("passed", "skipped", "failed")
# Directories whose Python files are user-facing examples (tests/ excluded).
EXAMPLE_ROOTS = ("quickstart", "migration", "templates", "performance", "fundamentals", "pitfalls")
PREFIX = "cookbook_"

# A statement that claims live verification. Matched case-insensitively, clause by
# clause, in the report's statements and in Markdown paragraphs the patch adds.
LIVE_CLAIM = re.compile(
    r"\b(?:verified|tested|confirmed|validated|works?|ran|passe[sd])\b[^.\n]{0,40}?"
    r"\b(?:on|against|with)\s+(?:a\s+)?(?:live\s+|running\s+)?CUBRID\b"
    r"|\b(?:make\s+verify|goldens?|live\s+(?:CUBRID\s+)?(?:tests?|suites?|run))\s+"
    r"(?:passe[sd]|succeeded|(?:is|are)\s+green)\b",
    re.IGNORECASE,
)
NOT_VERIFIED = re.compile(r"\bnot\s+(?:been\s+)?(?:verified|run|tested)\b", re.IGNORECASE)
# Added SQL that builds a query from values: an f-string, ``.format()`` or ``%``
# applied to text with a query keyword. Identifiers from fixed constants in DDL or
# ``SET`` statements are not matched; values must use ``?`` markers.
SQL_TEXT = r"(?:SELECT\b|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|\bWHERE\b|\bVALUES\b)"
TRIPLE_SQL = re.compile(
    r"""(?P<f>\b[fF][rR]?|\b[rR][fF])?(?P<q>\"\"\"|\'\'\')(?P<body>.*?)(?P=q)"""
    r"""(?P<op>\s*(?:\.format\(|%\s*[\w(]))?""",
    re.DOTALL,
)
STRING_START = re.compile(r"""[rRbBfF]{0,2}["']""")
STRING_LITERAL = re.compile(r"""(?<![\w"'])([rRbBfF]{0,2})(["'])((?:\\.|(?!\2).)*)\2""")
SQL_INTERPOLATION = re.compile(
    rf"""\bf(?P<q>["']).*{SQL_TEXT}.*\{{"""
    rf"""|(?P<r>["']).*{SQL_TEXT}.*(?P=r)\s*(?:\.format\(|%\s*[\w(])""",
    re.IGNORECASE,
)
# A secret written into the source: a non-empty password literal, a private key
# or a token with a well-known prefix. ``""`` and environment lookups are fine.
SECRET = re.compile(
    r"""\bpass(?:word|wd)\b["']?\s*[:=]\s*["'][^"'\s]+["']"""
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\b(?:ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}|\bAKIA[0-9A-Z]{16}\b"
    r"|\bsk-[A-Za-z0-9]{20,}",
    re.IGNORECASE,
)
CREATE_TABLE = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)", re.IGNORECASE
)
TABLENAME = re.compile(r"""__tablename__\s*=\s*["'](\w+)["']""")
REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


class EvalError(Exception):
    """A malformed task or candidate artifact."""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvalError(f"{path}: {exc}") from exc


def parse_patch(text: str) -> dict[str, list[str]]:
    """Map each file the patch touches to the lines it adds (without the ``+``)."""
    return {
        path: [line for kind, line in lines if kind == "+"] for path, lines in _hunks(text).items()
    }


def _hunks(text: str) -> dict[str, list[tuple[str, str]]]:
    """Map each file to its added (``+``) and context (`` ``) lines, in diff order.

    The file name comes from the ``+++``/``---``/``rename to`` header lines (or
    the ``diff --git`` line when it names one path twice); a rename lists its
    source as well, with no lines, while a copy's unchanged source is not listed. A header that names no
    file raises EvalError rather than dropping the file from the scope check.
    """
    files: dict[str, list[tuple[str, str]]] = {}
    lines: list[tuple[str, str]] = []
    paths: dict[str, str] = {}
    started = False
    header = False  # between ``diff --git`` and the file's first ``@@`` hunk

    def finish() -> None:
        if not started:
            return
        path = paths.get("+++") or paths.get("rename") or paths.get("---") or paths.get("git")
        if path is None:
            raise EvalError(f"cannot tell which file a diff section changes: {paths}")
        files.setdefault(path, []).extend(lines)
        # A rename also removes its source, which the scope check must see too.
        if paths.get("from"):
            files.setdefault(paths["from"], [])

    for line in text.splitlines():
        if line.startswith("diff --git "):
            finish()
            started, header, lines, paths = True, True, [], {}
            rest = line[len("diff --git ") :]
            half = (len(rest) - 1) // 2
            if '"' not in rest and rest[:2] == "a/" and rest == f"{rest[:half]} b/{rest[2:half]}":
                paths["git"] = rest[2:half]
            continue
        if not started:
            continue
        if header:
            if line.startswith(("+++ ", "--- ")):
                name = _diff_path(line[4:])
                if name is not None:
                    paths[line[:3]] = name
            elif line.startswith("rename from "):
                paths["from"] = _diff_path(line[len("rename from ") :], prefixed=False) or ""
            elif line.startswith(("rename to ", "copy to ")):
                paths["rename"] = _diff_path(line.split(" to ", 1)[1], prefixed=False) or ""
            elif line.startswith("@@"):
                header = False
                lines.append(("@", line))
            continue
        if line.startswith("@@"):
            lines.append(("@", line))
        elif line[:1] in ("+", " "):
            lines.append((line[:1], line[1:]))
    finish()
    return files


def _diff_path(name: str, prefixed: bool = True) -> str | None:
    """A path from a diff header line; ``None`` for ``/dev/null``."""
    name = name.rstrip("\t")
    if name.startswith('"'):
        try:
            name = ast.literal_eval("b" + name).decode("utf-8")
        except (SyntaxError, ValueError, UnicodeDecodeError) as exc:
            raise EvalError(f"unreadable quoted path in the diff: {name}") from exc
    if name == "/dev/null":
        return None
    if prefixed:
        if name[:2] not in ("a/", "b/"):
            raise EvalError(f"diff path without an a/ or b/ prefix: {name}")
        name = name[2:]
    return name


def _matches(path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in globs)


def _criterion(status: str, detail: str) -> dict[str, str]:
    return {"status": status, "detail": detail}


def _check_report(report: Any) -> None:
    if not isinstance(report, dict) or not isinstance(report.get("tests"), list):
        raise EvalError("report.json must be an object with a 'tests' list")
    statements = report.get("statements", [])
    if not isinstance(statements, list) or not all(isinstance(t, str) for t in statements):
        raise EvalError("report.json 'statements' must be a list of strings")
    for entry in report["tests"]:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(key), str) for key in ("command", "evidence", "result")
        ):
            raise EvalError(
                f"report.json test entries need string command/evidence/result: {entry!r}"
            )


def _clauses(text: str) -> list[str]:
    """Split a statement into clauses, so one disclaimer cannot excuse another claim."""
    return [
        c
        # Code spans are unwrapped first: "`make verify` passed" is still a claim.
        for c in re.split(
            r"[.;:!?](?:\s+|$)|,\s+|\s+(?:and|but|while|although|whereas)\s+",
            text.replace("`", ""),
        )
        if c
    ]


def _changelog(task: dict[str, Any], patch: str) -> dict[str, str]:
    expected = task["changelog"]
    lines = _hunks(patch).get("CHANGELOG.md", [])
    if expected is None:
        # The task's base predates a required entry: one is neither needed nor penalized.
        return _criterion("pass", "the task requires no CHANGELOG entry")
    header = f"### {expected['section']}"
    issue = task["issue"]
    entry = next((i for i, (kind, text) in enumerate(lines) if kind == "+" and issue in text), None)
    if entry is None:
        return _criterion("fail", f"no CHANGELOG entry citing {issue}")
    # The nearest heading before the entry, added or kept as diff context, is its section.
    section = next(
        (text for kind, text in reversed(lines[:entry]) if kind != "@" and text.startswith("### ")),
        None,
    )
    if section is None:
        return _criterion("fail", f"cannot tell the entry's section; expected {header}")
    if section.strip() != header:
        return _criterion("fail", f"the CHANGELOG entry is under {section.strip()}, not {header}")
    return _criterion("pass", f"CHANGELOG entry under {header} cites {issue}")


def _added_paragraphs(hunks: dict[str, list[tuple[str, str]]]) -> list[str]:
    """Added Markdown text, one entry per paragraph, so a wrapped claim reads as one.

    A blank line, a kept (context) line, a new hunk and a new file each end a
    paragraph, so text from different places is never joined.
    """
    paragraphs = []
    for path, lines in sorted(hunks.items()):
        if not path.endswith(".md"):
            continue
        current: list[str] = []
        for kind, text in [*lines, ("@", "")]:
            if kind == "+" and text.strip():
                current.append(text.strip())
                continue
            if current:
                paragraphs.append(" ".join(current))
                current = []
    return paragraphs


def pytest_outcome(exit_code: int, output: str) -> str:
    """``passed`` only when pytest ran at least one test and none failed.

    An all-skipped run (an integration test without a configured server) exits 0
    and a run that collected nothing exits 5; both are ``skipped``, never proof.
    """
    tail = output.strip().splitlines()[-1:] or [""]
    passed = re.search(r"\b(\d+) passed\b", tail[0])
    if exit_code == 0 and passed and int(passed.group(1)) > 0:
        return "passed"
    if exit_code in (0, 5):
        return "skipped"
    return "failed"


def dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def validate_task(task: Any, where: str = "task") -> list[str]:
    """Return one message per problem in a task manifest."""
    if not isinstance(task, dict):
        return [f"{where}: must be a JSON object"]
    errors = []
    missing = sorted(TASK_KEYS - set(task))
    unknown = sorted(set(task) - TASK_KEYS)
    if missing:
        errors.append(f"{where}: missing keys {missing}")
    if unknown:
        errors.append(f"{where}: unknown keys {unknown}")
    if task.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{where}: schema_version must be {SCHEMA_VERSION}")
    for key in ("fix_commit", "base_sha"):
        if not re.fullmatch(r"[0-9a-f]{40}", str(task.get(key, ""))):
            errors.append(f"{where}: {key} must be a full 40-character commit SHA")
    if not re.fullmatch(r"#[0-9]+", str(task.get("issue", ""))):
        errors.append(f"{where}: issue must look like '#123'")
    if not isinstance(task.get("recipe"), str) or not task.get("recipe"):
        errors.append(f"{where}: recipe must name the recipe directory")
    for key, minimum in (("allowed_files", 1), ("non_goals", 1), ("required_tests", 0)):
        value = task.get(key)
        if (
            not isinstance(value, list)
            or len(value) < minimum
            or not all(isinstance(v, str) and v for v in value)
        ):
            errors.append(f"{where}: {key} must be a list of at least {minimum} strings")
    goldens = task.get("goldens")
    if not isinstance(goldens, list) or not all(
        isinstance(g, str) and re.search(r"/expected/[^/]+\.expected$", g) for g in goldens
    ):
        errors.append(f"{where}: goldens must list */expected/*.expected paths")
    hidden = task.get("hidden_tests")
    if (
        not isinstance(hidden, list)
        or not hidden
        or not all(isinstance(name, str) and re.fullmatch(r"test_\w+\.py", name) for name in hidden)
    ):
        errors.append(f"{where}: hidden_tests must be a non-empty list of test_*.py file names")
    validation = task.get("validation")
    if not isinstance(validation, dict):
        errors.append(f"{where}: validation must be an object")
    else:
        offline = validation.get("offline")
        if not isinstance(offline, list) or not all(
            isinstance(c, str) and c.startswith(PYTEST) for c in offline
        ):
            errors.append(
                f"{where}: validation.offline must be a list of {PYTEST.strip()!r} commands"
            )
        live = validation.get("live")
        if not isinstance(live, list) or not all(
            isinstance(c, str) and c.startswith(LIVE_PREFIXES) for c in live
        ):
            errors.append(f"{where}: validation.live must list 'make verify'/pytest commands")
    docs = task.get("docs")
    if not isinstance(docs, list) or not all(
        isinstance(group, list) and group and all(isinstance(g, str) and g for g in group)
        for group in docs
    ):
        errors.append(f"{where}: docs must be a list of non-empty file-glob groups")
    changelog = task.get("changelog")
    if changelog is not None and not (
        isinstance(changelog, dict) and isinstance(changelog.get("section"), str)
    ):
        errors.append(f"{where}: changelog must be null or {{'section': ...}}")
    evidence = task.get("evidence")
    if not isinstance(evidence, dict):
        errors.append(f"{where}: evidence must be an object")
    else:
        if evidence.get("live") not in ("absent", "present"):
            errors.append(f"{where}: evidence.live must be 'absent' or 'present'")
        required = evidence.get("required_kinds", [])
        if not isinstance(required, list) or any(k not in EVIDENCE_KINDS for k in required):
            errors.append(f"{where}: evidence.required_kinds must use {list(EVIDENCE_KINDS)}")
    if not isinstance(task.get("expected"), str) or not task.get("expected"):
        errors.append(f"{where}: expected must describe the expected result")
    return errors


def grade(task: dict[str, Any], patch: str, report: Any, results: Any | None) -> dict[str, Any]:
    """Score one candidate. Raises EvalError for a malformed report or results file."""
    _check_report(report)
    if results is not None:
        _check_results(results)
    hunks = _hunks(patch)
    files = {path: [t for kind, t in lines if kind == "+"] for path, lines in hunks.items()}
    changed = sorted(files)
    criteria: dict[str, dict[str, str]] = {}
    digest = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    same_patch = results is not None and (
        results["task"],
        results["base_sha"],
        results["patch_sha256"],
    ) == (task["id"], task["base_sha"], digest)
    # Live commands the runner saw pass for this exact patch (a skipped run is not one).
    live_passed = (
        {
            c["command"]
            for c in results["commands"]
            if c["kind"] == "live" and c["outcome"] == "passed"
        }
        if same_patch
        else set()
    )

    # Behavior: the task's offline and evaluator-owned commands, run by ``run``.
    if results is None:
        criteria["behavior"] = _criterion("not_run", "no results.json: offline tests not run")
    else:
        observed = {c["command"]: c["outcome"] for c in results["commands"]}
        wanted = task["validation"]["offline"] + hidden_commands(task)
        missing = [c for c in wanted if c not in observed]
        failed = [c for c in wanted if c in observed and observed[c] != "passed"]
        if not same_patch:
            criteria["behavior"] = _criterion(
                "fail", "results.json was recorded for another task, base SHA or patch"
            )
        elif not results["applied"]:
            criteria["behavior"] = _criterion("fail", "the patch did not apply at the base SHA")
        elif missing:
            criteria["behavior"] = _criterion("not_run", f"not run: {missing}")
        elif failed:
            criteria["behavior"] = _criterion("fail", f"failed or skipped: {failed}")
        else:
            criteria["behavior"] = _criterion("pass", "every offline and hidden command passed")

    if not task["required_tests"]:
        criteria["regression_test"] = _criterion("pass", "the task requires no test change")
    else:
        tests = [path for path in changed if _matches(path, task["required_tests"])]
        criteria["regression_test"] = (
            _criterion("pass", f"tests changed: {tests}")
            if tests
            else _criterion("fail", f"no change to {task['required_tests']}")
        )

    extra = [path for path in changed if not _matches(path, task["allowed_files"])]
    criteria["scope"] = (
        _criterion("fail", f"outside the allowed files: {extra}")
        if extra
        else _criterion("pass", "every changed file is allowed")
    )

    unmet = [group for group in task["docs"] if not any(_matches(p, group) for p in changed)]
    criteria["docs"] = (
        _criterion("fail", f"no change to any of {unmet}")
        if unmet
        else _criterion("pass", "affected documentation updated")
    )
    missing_goldens = [g for g in task["goldens"] if not files.get(g)]
    criteria["goldens"] = (
        _criterion("fail", f"golden not added or updated: {missing_goldens}")
        if missing_goldens
        else _criterion("pass", "every required golden is added or updated")
    )
    criteria["changelog"] = _changelog(task, patch)
    criteria["dependencies"] = _dependencies(hunks)
    criteria["safety"] = _safety(files, hunks)
    criteria["claims"] = _claims(task, hunks, report, live_passed)
    criteria["evidence"] = _evidence(task, report, live_passed)

    statuses = {c["status"] for c in criteria.values()}
    verdict = "fail" if "fail" in statuses else "incomplete" if "not_run" in statuses else "pass"
    return {
        "schema_version": SCHEMA_VERSION,
        "task": task["id"],
        "changed_files": changed,
        "criteria": criteria,
        "verdict": verdict,
    }


def _check_results(results: Any) -> None:
    if not isinstance(results, dict) or not isinstance(results.get("commands"), list):
        raise EvalError("results.json must be an object with a 'commands' list")
    for key in ("task", "base_sha", "patch_sha256"):
        if not isinstance(results.get(key), str):
            raise EvalError(f"results.json needs a string {key!r}")
    if not isinstance(results.get("applied"), bool):
        raise EvalError("results.json needs a boolean 'applied'")
    for entry in results["commands"]:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("command"), str)
            or entry.get("kind") not in COMMAND_KINDS
            or entry.get("outcome") not in OUTCOMES
            or not isinstance(entry.get("exit_code"), int)
        ):
            raise EvalError(f"results.json command entries are malformed: {entry!r}")


def hidden_commands(task: dict[str, Any]) -> list[str]:
    """The commands that run the task's evaluator-owned tests inside the worktree."""
    return [f"{PYTEST}-q -p no:cacheprovider tests/{name}" for name in task["hidden_tests"]]


def _is_example(path: str) -> bool:
    parts = path.split("/")
    return parts[0] in EXAMPLE_ROOTS and "tests" not in parts and path.endswith(".py")


def _multiline_sql(path: str, lines: list[tuple[str, str]]) -> list[str]:
    """Triple-quoted SQL built from values that an added line takes part in.

    Each hunk's new text (kept and added lines) is searched on its own, so a
    multiline f-string or ``.format()`` query is seen whole, and hunks never join.
    """
    problems = []
    hunks: list[list[tuple[str, str]]] = [[]]
    for kind, text in lines:
        if kind == "@":
            hunks.append([])
        else:
            hunks[-1].append((kind, text))
    for hunk in hunks:
        text = "\n".join(t for _, t in hunk)
        added, offset = [], 0
        for kind, line in hunk:
            if kind == "+":
                added.append((offset, offset + len(line)))
            offset += len(line) + 1
        problems += _adjacent_sql(path, hunk)
        for match in TRIPLE_SQL.finditer(text):
            if not re.search(SQL_TEXT, match.group("body"), re.IGNORECASE):
                continue
            built = (match.group("f") and "{" in match.group("body")) or match.group("op")
            if built and any(a < match.end() and b > match.start() for a, b in added):
                problems.append(f"{path}: multiline SQL built by string interpolation")
    return problems


def _adjacent_sql(path: str, hunk: list[tuple[str, str]]) -> list[str]:
    """SQL split over adjacent string literals, one of them an interpolating f-string.

    A run is a line followed by the lines that start with a string literal (Python
    joins adjacent literals), such as ``cur.execute("... VALUES ("`` then
    ``f"{value})"``. A run is checked only when an added line is part of it.
    """
    problems = []
    runs: list[list[tuple[str, str]]] = []
    for kind, line in hunk:
        if runs and STRING_START.match(line.strip()):
            runs[-1].append((kind, line))
        else:
            runs.append([(kind, line)])
    for run in runs:
        if len(run) < 2 or not any(kind == "+" for kind, _ in run):
            continue
        literals = STRING_LITERAL.findall(" ".join(line for _, line in run))
        joined = "".join(body for _, _, body in literals)
        interpolated = any("f" in prefix.lower() and "{" in body for prefix, _, body in literals)
        if interpolated and re.search(SQL_TEXT, joined, re.IGNORECASE):
            problems.append(f"{path}: SQL built from adjacent strings with interpolation")
    return problems


def _safety(files: dict[str, list[str]], hunks: dict[str, list[tuple[str, str]]]) -> dict[str, str]:
    """Added lines: no value interpolated into SQL, no secret, ``cookbook_`` tables."""
    problems = []
    for path in sorted(hunks):
        if path.endswith(".py"):
            problems += _multiline_sql(path, hunks[path])
    for path, lines in sorted(files.items()):
        for text in lines:
            if path.endswith(".py") and SQL_INTERPOLATION.search(text):
                problems.append(f"{path}: SQL built by string interpolation: {text.strip()!r}")
            if not path.startswith("agent-evals/") and SECRET.search(text):
                problems.append(f"{path}: hardcoded secret: {text.strip()!r}")
            if _is_example(path):
                for name in CREATE_TABLE.findall(text) + TABLENAME.findall(text):
                    if not name.lower().startswith(PREFIX):
                        problems.append(f"{path}: table {name!r} lacks the {PREFIX} prefix")
    if problems:
        return _criterion("fail", "; ".join(problems))
    return _criterion("pass", "no interpolated SQL, secret or unprefixed table added")


def _dependencies(hunks: dict[str, list[tuple[str, str]]]) -> dict[str, str]:
    """Every requirement the patch adds or changes is named in added documentation."""
    docs = " ".join(_added_paragraphs(hunks)).lower().replace("_", "-")
    problems = []
    for path, lines in sorted(hunks.items()):
        if not re.search(r"(?:^|/)requirements[^/]*\.txt$", path):
            continue
        for kind, text in lines:
            match = REQUIREMENT.match(text) if kind == "+" else None
            if match and not text.lstrip().startswith(("#", "-")):
                name = match.group(1).lower().replace("_", "-")
                if name not in docs:
                    problems.append(f"{path}: {name} is not mentioned in the added documentation")
    if problems:
        return _criterion("fail", "; ".join(problems))
    return _criterion("pass", "every added or changed requirement is documented")


def _claims(
    task: dict[str, Any],
    files: dict[str, list[tuple[str, str]]],
    report: dict[str, Any],
    live_passed: set[str],
) -> dict[str, str]:
    statements = report.get("statements", [])
    problems = []
    if not live_passed:
        # Each clause on its own: "make verify passed. Suites were not run." still
        # claims a live result in its first sentence.
        for text in statements + _added_paragraphs(files):
            for clause in _clauses(text):
                if LIVE_CLAIM.search(clause) and not NOT_VERIFIED.search(clause):
                    problems.append(f"live claim without live evidence: {clause.strip()!r}")
    unbacked = [c for c in task["validation"]["live"] if c not in live_passed]
    for command in unbacked:
        entry = next((t for t in report["tests"] if t["command"] == command), None)
        if entry is None or entry["result"] not in ("not run", "failed"):
            problems.append(f"live check {command!r} is not reported as 'not run' or 'failed'")
    if unbacked and not any(NOT_VERIFIED.search(s) for s in statements):
        problems.append("the report does not say what was not verified")
    if problems:
        return _criterion("fail", "; ".join(sorted(set(problems))))
    return _criterion("pass", "claims match the recorded evidence")


def _evidence(
    task: dict[str, Any], report: dict[str, Any], live_passed: set[str]
) -> dict[str, str]:
    problems = []
    kinds = set()
    for entry in report["tests"]:
        kind, result = entry["evidence"], entry["result"]
        if kind not in EVIDENCE_KINDS or result not in RESULTS:
            problems.append(f"bad report entry {entry!r}")
            continue
        if result == "passed":
            kinds.add(kind)
            # A live check is live whatever the label: reported as passed offline
            # evidence, it would bypass the live-run requirement.
            command = entry["command"]
            if kind not in LIVE_KINDS and (
                command in task["validation"]["live"] or command.startswith("make verify")
            ):
                problems.append(f"live check {command!r} reported as {kind} evidence")
            # Live evidence counts only for a live command the runner saw pass.
            if kind in LIVE_KINDS and entry["command"] not in live_passed:
                problems.append(
                    f"{kind} reported as passed for {entry['command']!r}"
                    " without a passing recorded live run of that command"
                )
    for kind in task["evidence"].get("required_kinds", []):
        if kind not in kinds:
            problems.append(f"no passed {kind} evidence")
    if problems:
        return _criterion("fail", "; ".join(problems))
    return _criterion("pass", f"evidence kinds: {sorted(kinds)}")


def _bounded(argv: list[str], cwd: Path, timeout: float) -> tuple[int, str]:
    """Run a command in its own process group; on timeout kill the whole group.

    A timed-out command reports exit code 124 (``failed``), so a hung recipe or
    test cannot keep ``run`` from recording results and removing the worktree.
    """
    with subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    ) as proc:
        try:
            output, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return 124, ""
    return proc.returncode, output


def run(
    task: dict[str, Any], patch: str, repo: Path = ROOT, timeout: float = 600.0
) -> dict[str, Any]:
    """Apply the patch at the base SHA in a throwaway worktree and run the offline tests."""
    commands = [(c, "offline") for c in task["validation"]["offline"]]
    commands += [(c, "hidden") for c in hidden_commands(task)]
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "task": task["id"],
        "base_sha": task["base_sha"],
        "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
        "applied": False,
        "commands": [],
    }
    with tempfile.TemporaryDirectory(prefix="agent-eval-") as tmp:
        worktree = Path(tmp) / "worktree"
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "worktree",
                "add",
                "--detach",
                str(worktree),
                task["base_sha"],
            ],
            check=True,
            capture_output=True,
        )
        try:
            patch_file = Path(tmp) / "candidate.diff"
            patch_file.write_text(patch, encoding="utf-8")
            applied = subprocess.run(
                ["git", "-C", str(worktree), "apply", "--whitespace=nowarn", str(patch_file)],
                capture_output=True,
            )
            result["applied"] = applied.returncode == 0
            if result["applied"]:
                (worktree / "tests").mkdir(exist_ok=True)
                for name in task["hidden_tests"]:
                    source = EVALS / "tasks" / task["id"] / "hidden" / name
                    (worktree / "tests" / name).write_bytes(source.read_bytes())
                for command, kind in commands:
                    argv = shlex.split(command)
                    if argv[:1] == ["python"]:  # the interpreter running this script
                        argv[0] = sys.executable
                    code, output = _bounded(argv, worktree, timeout)
                    result["commands"].append(
                        {
                            "command": command,
                            "kind": kind,
                            "exit_code": code,
                            "outcome": pytest_outcome(code, output),
                        }
                    )
        finally:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", str(worktree)],
                capture_output=True,
            )
    return result


def load_task(task_id: str, root: Path = EVALS) -> dict[str, Any]:
    path = root / "tasks" / task_id / "task.json"
    task = load_json(path)
    errors = validate_task(task, str(path.relative_to(root.parent)))
    if not errors:
        errors = [
            f"{path.parent.name}: hidden test {name} is missing"
            for name in task["hidden_tests"]
            if not (path.parent / "hidden" / name).is_file()
        ]
    if errors:
        raise EvalError("; ".join(errors))
    return task


def check(root: Path = EVALS) -> list[str]:
    """Validate every task and re-grade every fixture against its expected verdict."""
    problems = []
    tasks = sorted(p.parent for p in (root / "tasks").glob("*/task.json"))
    if not tasks:
        return [f"no tasks under {root / 'tasks'}"]
    for task_dir in tasks:
        try:
            task = load_task(task_dir.name, root)
        except EvalError as exc:
            problems.append(str(exc))
            continue
        if task["id"] != task_dir.name:
            problems.append(f"{task_dir.name}: id is {task['id']!r}")
        fixtures = sorted(p for p in (task_dir / "fixtures").glob("*") if p.is_dir())
        if not fixtures:
            problems.append(f"{task_dir.name}: no fixtures")
        for fixture in fixtures:
            results = fixture / "results.json"
            try:
                got = grade(
                    task,
                    (fixture / "patch.diff").read_text(encoding="utf-8"),
                    load_json(fixture / "report.json"),
                    load_json(results) if results.exists() else None,
                )
                expected = load_json(fixture / "expected.json")
            except (EvalError, OSError) as exc:
                problems.append(f"{task_dir.name}/{fixture.name}: {exc}")
                continue
            if got["verdict"] != expected.get("verdict") or any(
                got["criteria"].get(name, {}).get("status") != status
                for name, status in expected.get("criteria", {}).items()
            ):
                problems.append(f"{task_dir.name}/{fixture.name}: graded {dump(got)}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate every task manifest")
    sub.add_parser("check", help="re-grade every recorded fixture")
    r = sub.add_parser("run", help="dry run: apply a patch at the base SHA and run the tests")
    r.add_argument("--task", required=True)
    r.add_argument("--patch", required=True, type=Path)
    r.add_argument("--output", required=True, type=Path)
    g = sub.add_parser("grade", help="grade one candidate")
    g.add_argument("--task", required=True)
    g.add_argument("--patch", required=True, type=Path)
    g.add_argument("--report", required=True, type=Path)
    g.add_argument("--results", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            for task_dir in sorted(p.parent for p in (EVALS / "tasks").glob("*/task.json")):
                load_task(task_dir.name)
            print("agent-evals: every task manifest is valid")
            return 0
        if args.command == "check":
            problems = check()
            for problem in problems:
                print(problem, file=sys.stderr)
            if problems:
                return 1
            print("agent-evals: every fixture grades as expected")
            return 0
        task = load_task(args.task)
        if args.command == "run":
            observed = run(task, args.patch.read_text(encoding="utf-8"))
            args.output.write_text(dump(observed), encoding="utf-8")
            print(f"agent-eval: wrote {args.output}")
            return 0
        result = grade(
            task,
            args.patch.read_text(encoding="utf-8"),
            load_json(args.report),
            load_json(args.results) if args.results else None,
        )
    except (EvalError, OSError, subprocess.CalledProcessError) as exc:
        print(f"agent-eval: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(dump(result))
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
