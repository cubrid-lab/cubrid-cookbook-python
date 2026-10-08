"""Every executing workflow job carries an explicit, bounded timeout (#228).

GitHub's default job limit is 360 minutes. Jobs that call a reusable workflow
cannot set ``timeout-minutes``; externally owned callees are an exact allowlist.
Text-based on purpose: the offline suite does not install a YAML parser, so jobs
are read from the repository's two-space workflow layout.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"

MAX_TIMEOUT_MINUTES = 180
GATE_MAX_TIMEOUT_MINUTES = 10
EXTERNAL_REUSABLE_CALLERS = {
    "cubrid-lab/.github/.github/workflows/doc-lint.yml",
    "cubrid-lab/.github/.github/workflows/live-smoke.yml",
}
GATES = {("ci.yml", "ci-gate")}

JOB_HEADER = re.compile(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$")


def parse_jobs(text: str) -> dict[str, list[str]]:
    """Return each top-level job's body lines (indented four spaces or more)."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(r"^jobs:\s*(?:#.*)?$", line)]
    if not starts:
        return {}
    jobs: dict[str, list[str]] = {}
    current = None
    for line in lines[starts[0] + 1 :]:
        if line and not line.startswith(" ") and not line.startswith("#"):
            break  # next top-level key
        header = JOB_HEADER.match(line)
        if header:
            current = header.group(1)
            jobs[current] = []
        elif re.match(r"^  \S", line) and not line.lstrip().startswith("#"):
            # A job header this parser does not understand must not be merged into
            # the previous job, where it could borrow that job's timeout.
            raise ValueError(f"unrecognized job header: {line!r}")
        elif current is not None:
            jobs[current].append(line)
    return jobs


def job_key(body: list[str], key: str) -> str | None:
    for line in body:
        match = re.match(rf"^    {re.escape(key)}:\s*(.*?)\s*(?:\s#.*)?$", line)
        if match:
            return match.group(1)
    return None


def problems(name: str, text: str) -> list[str]:
    found = []
    for job, body in parse_jobs(text).items():
        uses = job_key(body, "uses")
        if uses is not None:
            target = uses.split("@", 1)[0]
            if not target.startswith("./") and target not in EXTERNAL_REUSABLE_CALLERS:
                found.append(f"{name}:{job} calls unlisted external workflow {target}")
            continue
        timeout = job_key(body, "timeout-minutes")
        if timeout is None or not timeout.isdigit():
            found.append(f"{name}:{job} has no integer timeout-minutes (default is 360)")
        elif not 1 <= int(timeout) <= MAX_TIMEOUT_MINUTES:
            found.append(f"{name}:{job} timeout {timeout} out of range")
    return found


class WorkflowTimeoutTest(unittest.TestCase):
    def test_every_executing_job_has_a_bounded_timeout(self) -> None:
        paths = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
        self.assertTrue(paths)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertTrue(parse_jobs(text), "no jobs parsed; the check would be vacuous")
                self.assertEqual(problems(path.name, text), [])

    def test_parser_sees_every_job(self) -> None:
        # Guards against a parser that silently finds nothing.
        jobs = parse_jobs((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
        self.assertIn("ci-gate", jobs)
        self.assertGreaterEqual(len(jobs), 10)

    def test_local_callees_and_allowlist_are_current(self) -> None:
        callers = set()
        for path in WORKFLOWS.glob("*.y*ml"):
            for body in parse_jobs(path.read_text(encoding="utf-8")).values():
                uses = job_key(body, "uses")
                if uses is None:
                    continue
                target = uses.split("@", 1)[0]
                if target.startswith("./"):
                    self.assertTrue((ROOT / target).is_file(), target)
                else:
                    callers.add(target)
        self.assertEqual(callers, EXTERNAL_REUSABLE_CALLERS)

    def test_gates_keep_always_and_a_short_timeout(self) -> None:
        for wf, name in sorted(GATES):
            body = parse_jobs((WORKFLOWS / wf).read_text(encoding="utf-8"))[name]
            with self.subTest(gate=f"{wf}:{name}"):
                self.assertIn(job_key(body, "if"), {"always()", "${{ always() }}"})
                timeout = job_key(body, "timeout-minutes") or ""
                self.assertTrue(timeout.isdigit() and 1 <= int(timeout) <= GATE_MAX_TIMEOUT_MINUTES)

    def test_checker_flags_missing_step_level_only_and_unlisted_callers(self) -> None:
        sample = textwrap_dedent(
            """
            jobs:
              ok:
                runs-on: ubuntu-latest
                timeout-minutes: 5
              missing:
                runs-on: ubuntu-latest
                steps:
                  - run: echo hi
                    timeout-minutes: 5
              caller:
                uses: someone/else/.github/workflows/x.yml@abc
            """
        )
        found = problems("sample.yml", sample)
        self.assertEqual(len(found), 2, found)
        self.assertTrue(any("missing" in f for f in found))
        self.assertTrue(any("unlisted external" in f for f in found))


def textwrap_dedent(text: str) -> str:
    import textwrap

    return textwrap.dedent(text).lstrip("\n")


if __name__ == "__main__":
    unittest.main()
