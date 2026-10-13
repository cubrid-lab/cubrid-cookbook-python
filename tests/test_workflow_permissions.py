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

USES_CHECKOUT = re.compile(r"^(\s*)(- )?uses:\s*[\"']?actions/checkout@")

# Every write grant must be listed: workflow file -> {(scope, permission)}.
# ``scope`` is "top" for the workflow-level block or the job id for a job-level one.
WRITE_ALLOWLIST: dict[str, set[tuple[str, str]]] = {
    # Only the Pages deploy job; the build job (pip install, mkdocs) stays read-only (#330).
    "docs.yml": {("deploy", "pages"), ("deploy", "id-token")},
    # The advisory driver-main lane (#239) reports to one tracking issue.
    "ci.yml": {("driver-main-advisory", "issues")},
    "driver-main.yml": {("report", "issues")},
    "dependabot-auto-merge.yml": {
        ("auto-merge", "contents"),
        ("auto-merge", "pull-requests"),
    },
}

AUTO_MERGE_CONDITION = (
    "github.actor == 'dependabot[bot]' && github.event.pull_request.user.login == 'dependabot[bot]'"
)


def strip_comments(text: str) -> str:
    """Drop YAML ``#`` comments (a ``#`` at line start or after whitespace)."""
    return "\n".join(re.sub(r"(^|\s)#.*$", r"\1", line) for line in text.splitlines())


def issue_create_commands(text: str) -> list[str]:
    """Return every ``gh issue create`` command, with shell continuations joined."""
    joined = re.sub(r"\\\n\s*", " ", strip_comments(text))
    return [
        re.sub(r"\s+", " ", match.group(0)).strip()
        for line in joined.splitlines()
        for match in re.finditer(r"\bgh\s+issue\s+create\b.*", line)
    ]


def label_problems(command: str) -> list[str]:
    """Return why ``command`` lacks exactly one canonical priority and size label."""
    labels = [
        label.strip("\"'") for label in re.findall(r"--label[ =](\"[^\"]+\"|'[^']+'|\S+)", command)
    ]
    found = []
    for kind, pattern in (
        ("priority", r"priority: (critical|high|medium|low)"),
        ("size", r"size: (XS|S|M|L|XL)"),
    ):
        count = sum(bool(re.fullmatch(pattern, label)) for label in labels)
        if count != 1:
            found.append(f"{count} {kind} labels in {labels}")
    return found


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
    found = []
    scope = "top"
    allowed = WRITE_ALLOWLIST.get(name, set())
    in_jobs = False
    for line in strip_comments(text).splitlines():
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
            continue
        header = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if in_jobs and header:
            scope = header.group(1)
        if re.search(r"\bwrite-all\b", line):
            found.append(f"{name} uses write-all: {line.strip()}")
        for perm in re.findall(r"([A-Za-z][A-Za-z-]*):\s*write(?![\w-])", line):
            if (scope, perm) not in allowed:
                found.append(f"{name} grants unlisted write: {scope}/{perm}")
    return found


def auto_merge_problems(text: str) -> list[str]:
    found = []
    top = top_level_permissions(text) or []
    if any("write" in entry for entry in top):
        found.append("auto-merge workflow grants write permissions at workflow level")
    body = parse_jobs(text).get("auto-merge")
    if body is None:
        return ["auto-merge job missing"]
    joined = "\n".join(body)
    stripped = strip_comments("\n".join(body)).splitlines()
    condition = []
    capture = False
    for line in stripped:
        if re.match(r"^    if:", line):
            capture = True
            condition.append(re.sub(r"^    if:\s*[>|][-+]?", "", line).replace("if:", "", 1))
        elif capture and re.match(r"^    \S", line):
            break
        elif capture:
            condition.append(line)
    cond = " ".join(" ".join(condition).split())
    if cond != AUTO_MERGE_CONDITION:
        found.append(
            f"auto-merge if: is not exactly the dependabot actor && author check: {cond!r}"
        )
    code = strip_comments(text)
    if re.search(r"uses:\s*[\"']?actions/checkout", code):
        found.append("auto-merge workflow checks out code under pull_request_target")
    if re.search(r"\bhead\.(?:sha|ref)\b|\bhead_ref\b", code):
        found.append("auto-merge workflow references the PR head sha/ref")
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
            text = strip_comments(path.read_text(encoding="utf-8"))
            if re.search(r"\bgit\s+push\b", text):
                self.assertTrue(
                    any(name == path.name for name, _ in PUSHING_CHECKOUTS),
                    f"{path.name} pushes but is not on the allowlist",
                )

    def test_dependabot_auto_merge_guard(self) -> None:
        text = (WORKFLOWS / "dependabot-auto-merge.yml").read_text(encoding="utf-8")
        self.assertEqual(auto_merge_problems(text), [])

    def test_automated_issues_carry_priority_and_size_labels(self) -> None:
        # AGENTS.md: an issue gets exactly one canonical priority and size label at
        # creation, including issues a workflow opens (#330).
        creates = [
            (f"{path.name}: {command[:60]}", command)
            for path in workflow_paths()
            for command in issue_create_commands(path.read_text(encoding="utf-8"))
        ]
        self.assertTrue(creates, "no workflow creates an issue; the check would be vacuous")
        for where, command in creates:
            with self.subTest(where=where):
                self.assertEqual(label_problems(command), [])

    def test_issue_create_parser_follows_shell_continuations(self) -> None:
        split = 'run: |\n  gh issue \\\n    create --title "t" \\\n    --label ci\n'
        self.assertEqual(issue_create_commands(split), ['gh issue create --title "t" --label ci'])
        self.assertTrue(label_problems(issue_create_commands(split)[0]))
        good = "gh issue create \\\n  --label \"priority: low\" \\\n  --label 'size: XS' --body x\n"
        self.assertEqual([label_problems(c) for c in issue_create_commands(good)], [[]])
        self.assertTrue(label_problems('gh issue create --label "priority: low"'))
        self.assertEqual(issue_create_commands("# gh issue create in a comment\n"), [])

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
        self.assertTrue(auto_merge_problems(weak))
        self.assertTrue(permission_problems("x.yml", "permissions: write-all\n"))
        self.assertTrue(permission_problems("x.yml", "permissions:\n  contents: write\n"))
        self.assertTrue(permission_problems("docs.yml", "permissions:\n  pages: write\n"))
        deploy_only = (
            "permissions:\n  contents: read\njobs:\n  build:\n    runs-on: x\n"
            "  deploy:\n    permissions:\n      pages: write\n      id-token: write\n"
        )
        self.assertEqual(permission_problems("docs.yml", deploy_only), [])
        build_write = deploy_only.replace(
            "  build:\n    runs-on: x\n", "  build:\n    permissions:\n      pages: write\n"
        )
        self.assertTrue(permission_problems("docs.yml", build_write))
        quoted = 'jobs:\n  a:\n    steps:\n      - uses: "actions/checkout@abc"\n'
        self.assertEqual(len(checkout_problems("x.yml", quoted)), 1)
        self.assertEqual(len(checkout_problems("x.yml", quoted.replace('"', "'"))), 1)

    def test_auto_merge_checker_rejects_bypasses(self) -> None:
        real = (WORKFLOWS / "dependabot-auto-merge.yml").read_text(encoding="utf-8")
        mutations = {
            "or": real.replace("' &&", "' ||"),
            "comment": real.replace(
                "      github.event.pull_request.user.login == 'dependabot[bot]'",
                "      true # github.event.pull_request.user.login == 'dependabot[bot]'",
            ),
            "checkout": real.replace(
                "    steps:\n",
                "    steps:\n      - uses: actions/checkout@abc\n"
                "        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n",
            ),
        }
        for label, mutated in mutations.items():
            with self.subTest(mutation=label):
                self.assertNotEqual(mutated, real)
                self.assertTrue(auto_merge_problems(mutated))

    def test_unlisted_push_detection_pattern(self) -> None:
        pattern = re.compile(r"\bgit\s+push\b")
        self.assertTrue(pattern.search(strip_comments("run: make x; git push origin")))
        self.assertFalse(pattern.search(strip_comments("# git push is not used")))


if __name__ == "__main__":
    unittest.main()
