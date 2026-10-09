"""Workflow token and credential policy (#237).

* Every workflow declares top-level ``permissions`` (never the write-capable
  repository default), and ``ci.yml`` is read-only at the top.
* Every ``actions/checkout`` step sets ``persist-credentials: false`` unless it
  is on the explicit allowlist of steps that push.
* The Dependabot auto-merge job requires both the actor and the PR author to be
  ``dependabot[bot]`` and holds its write grants at job level only.

Text-based on purpose: the offline suite does not install a YAML parser.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from test_workflow_timeouts import job_key, parse_jobs

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"

# (workflow file, job) pairs whose checkout genuinely pushes and so needs the
# persisted token. Empty today: no workflow pushes.
PUSHING_CHECKOUTS: set[tuple[str, str]] = set()

USES_CHECKOUT = re.compile(r"^(\s*)(- )?uses:\s*actions/checkout@")


def workflow_paths() -> list[Path]:
    paths = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    assert paths, "no workflows found; the policy check would be vacuous"
    return paths


def top_level_permissions(text: str) -> list[str] | None:
    """Return the top-level permissions block lines (inline value first), or None."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = re.match(r"^permissions:\s*(.*?)\s*(?:#.*)?$", line)
        if not match:
            continue
        block = [match.group(1)] if match.group(1) else []
        for nxt in lines[i + 1 :]:
            if nxt.startswith("  ") or not nxt.strip() or nxt.lstrip().startswith("#"):
                if nxt.strip() and not nxt.lstrip().startswith("#"):
                    block.append(nxt.strip())
            else:
                break
        return block
    return None


def checkout_steps(text: str) -> list[tuple[int, list[str]]]:
    """Return (line number, step lines) for every actions/checkout step."""
    lines = text.splitlines()
    steps = []
    for i, line in enumerate(lines):
        match = USES_CHECKOUT.match(line)
        if not match:
            continue
        indent = len(match.group(1))
        # Keys of the step sit at the "uses" column (after "- " when inline).
        key_col = indent + 2 if match.group(2) else indent
        start = i
        if match.group(2) is None:
            # "uses:" is not the first key: walk back to the step's "- " line.
            while start > 0 and not re.match(rf"^{' ' * (indent - 2)}- ", lines[start]):
                start -= 1
        block = [lines[start], *lines[start + 1 : i]] if start < i else []
        block.append(line)
        for nxt in lines[i + 1 :]:
            if nxt.strip() and (len(nxt) - len(nxt.lstrip())) < key_col:
                break
            block.append(nxt)
        steps.append((i + 1, block))
    return steps


def owning_job(text: str, lineno: int) -> str | None:
    owner = None
    for i, line in enumerate(text.splitlines(), start=1):
        if i > lineno:
            break
        header = re.match(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$", line)
        if header:
            owner = header.group(1)
    return owner


def checkout_problems(name: str, text: str) -> list[str]:
    found = []
    for lineno, block in checkout_steps(text):
        job = owning_job(text, lineno)
        if (name, job) in PUSHING_CHECKOUTS:
            continue
        if not any(re.match(r"^\s*persist-credentials:\s*false\s*(?:#.*)?$", b) for b in block):
            found.append(f"{name}:{lineno} ({job}) checkout lacks persist-credentials: false")
    return found


def permission_problems(name: str, text: str) -> list[str]:
    block = top_level_permissions(text)
    if block is None:
        return [f"{name} has no top-level permissions (repository default may be write)"]
    return []


def auto_merge_problems(text: str) -> list[str]:
    found = []
    top = top_level_permissions(text) or []
    if any("write" in entry for entry in top):
        found.append("auto-merge workflow grants write permissions at workflow level")
    body = parse_jobs(text).get("auto-merge")
    if body is None:
        return ["auto-merge job missing"]
    joined = "\n".join(body)
    condition = []
    capture = False
    for line in body:
        if re.match(r"^    if:", line):
            capture = True
            condition.append(line)
        elif capture and re.match(r"^    \S", line):
            break
        elif capture:
            condition.append(line)
    cond = "\n".join(condition)
    if "github.actor == 'dependabot[bot]'" not in cond:
        found.append("auto-merge if: lost the actor check")
    if "github.event.pull_request.user.login == 'dependabot[bot]'" not in cond:
        found.append("auto-merge if: lacks the PR author check")
    if job_key(body, "permissions") != "" or "      pull-requests: write" not in joined:
        found.append("auto-merge job lacks job-level permissions")
    return found


class WorkflowPermissionsTest(unittest.TestCase):
    def test_every_workflow_has_explicit_top_level_permissions(self) -> None:
        for path in workflow_paths():
            with self.subTest(workflow=path.name):
                self.assertEqual(
                    permission_problems(path.name, path.read_text(encoding="utf-8")), []
                )

    def test_ci_is_read_only_at_the_top(self) -> None:
        text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        self.assertEqual(top_level_permissions(text), ["contents: read"])

    def test_called_workflows_get_what_they_declare(self) -> None:
        # doc-lint.yml declares contents + pull-requests read; a caller job
        # granting less (or inheriting a narrower top level) fails at startup.
        body = parse_jobs((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))["doc-lint"]
        joined = "\n".join(body)
        self.assertIn("      contents: read", joined)
        self.assertIn("      pull-requests: read", joined)

    def test_every_checkout_drops_credentials(self) -> None:
        total = 0
        for path in workflow_paths():
            text = path.read_text(encoding="utf-8")
            total += len(checkout_steps(text))
            with self.subTest(workflow=path.name):
                self.assertEqual(checkout_problems(path.name, text), [])
        self.assertGreaterEqual(total, 10, "checkout parser found too few steps")

    def test_pushing_allowlist_is_current(self) -> None:
        for name, job in PUSHING_CHECKOUTS:
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertIn(job, parse_jobs(text), f"stale allowlist entry {name}:{job}")
            self.assertRegex(text, r"git push", f"{name}:{job} does not push")

    def test_no_workflow_pushes_unlisted(self) -> None:
        for path in workflow_paths():
            text = path.read_text(encoding="utf-8")
            if re.search(r"^\s*(?:run:\s*)?git push\b", text, re.MULTILINE):
                self.assertTrue(
                    any(name == path.name for name, _ in PUSHING_CHECKOUTS),
                    f"{path.name} pushes but is not on the allowlist",
                )

    def test_dependabot_auto_merge_guard(self) -> None:
        text = (WORKFLOWS / "dependabot-auto-merge.yml").read_text(encoding="utf-8")
        self.assertEqual(auto_merge_problems(text), [])

    def test_checkers_detect_violations(self) -> None:
        self.assertTrue(permission_problems("x.yml", "on: push\njobs:\n  a:\n    steps: []\n"))
        bad = "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@abc\n"
        self.assertEqual(len(checkout_problems("x.yml", bad)), 1)
        bad = (
            "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@abc\n"
            "        with:\n          fetch-depth: 0\n"
        )
        self.assertEqual(len(checkout_problems("x.yml", bad)), 1)
        good = bad + "          persist-credentials: false\n"
        self.assertEqual(checkout_problems("x.yml", good), [])
        sibling = (
            "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@abc\n"
            "      - uses: actions/setup-python@abc\n"
            "        with:\n          persist-credentials: false\n"
        )
        self.assertEqual(len(checkout_problems("x.yml", sibling)), 1)
        weak = (
            "permissions: {}\njobs:\n  auto-merge:\n    if: github.actor == 'dependabot[bot]'\n"
            "    runs-on: x\n    permissions:\n      pull-requests: write\n"
        )
        self.assertTrue(any("author" in p for p in auto_merge_problems(weak)))


if __name__ == "__main__":
    unittest.main()
