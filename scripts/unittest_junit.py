#!/usr/bin/env python3
"""unittest_junit.py - Run ``unittest`` and also write a JUnit XML file (#461).

Usage: ``python scripts/unittest_junit.py JUNIT_XML [unittest arguments...]``, for
example ``python scripts/unittest_junit.py out.xml discover -s tests -p 'test_x.py' -v``.
The console output and exit status are those of ``python -m unittest``; the XML uses
the same shape as pytest's (``skipped`` with ``type="pytest.xfail"`` for an expected
failure) so ``scripts/report_results.py`` reads both alike. ``make test`` uses this
for its unittest suites because ``unittest`` has no JUnit output of its own.
"""

from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


def _names(test: unittest.TestCase) -> tuple[str, str]:
    # A failing subTest is reported against a wrapper; attribute it to its test.
    test = getattr(test, "test_case", test)
    classname, _, name = test.id().rpartition(".")
    return classname, name


def build_junit(result: unittest.TestResult, ids: list[unittest.TestCase]) -> ET.ElementTree:
    outcomes: dict[tuple[str, str], tuple[str, str]] = {}
    for test in ids:
        outcomes[_names(test)] = ("passed", "")
    for kind, entries in (
        ("skipped", result.skipped),
        ("xfail", result.expectedFailures),
        ("failure", result.failures),
        ("failure", [(t, "unexpected success") for t in result.unexpectedSuccesses]),
        ("error", result.errors),
    ):
        for test, detail in entries:
            outcomes[_names(test)] = (kind, str(detail))
    suite = ET.Element("testsuite", name="unittest", tests=str(len(outcomes)))
    for (classname, name), (kind, detail) in sorted(outcomes.items()):
        case = ET.SubElement(suite, "testcase", classname=classname, name=name)
        if kind == "skipped":
            ET.SubElement(case, "skipped", message=detail)
        elif kind == "xfail":
            ET.SubElement(case, "skipped", type="pytest.xfail", message=detail)
        elif kind in ("failure", "error"):
            ET.SubElement(
                case, kind, message=detail.splitlines()[-1] if detail else ""
            ).text = detail
    return ET.ElementTree(suite)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: unittest_junit.py JUNIT_XML [unittest arguments...]", file=sys.stderr)
        return 2
    junit = Path(argv[0])
    seen: list[unittest.TestCase] = []

    class Result(unittest.TextTestResult):
        def startTest(self, test: unittest.TestCase) -> None:  # noqa: N802
            seen.append(test)
            super().startTest(test)

    class Runner(unittest.TextTestRunner):
        resultclass = Result

        def run(self, test):  # noqa: ANN001, ANN201
            result = super().run(test)
            junit.parent.mkdir(parents=True, exist_ok=True)
            build_junit(result, seen).write(junit, encoding="utf-8", xml_declaration=True)
            return result

    program = unittest.main(
        module=None, argv=["unittest", *argv[1:]], testRunner=Runner, exit=False
    )
    return 0 if program.result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
