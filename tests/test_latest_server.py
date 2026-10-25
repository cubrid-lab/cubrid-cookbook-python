"""Weekly newest-stable CUBRID image check (#480): decision and workflow wiring."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import latest_server  # noqa: E402
from test_workflow_timeouts import parse_jobs  # noqa: E402

SMOKE = (ROOT / ".github/workflows/smoke-test.yml").read_text(encoding="utf-8")
REF_A = "cubrid/cubrid@sha256:" + "a" * 64
REF_B = "cubrid/cubrid@sha256:" + "b" * 64
REL_1146 = (
    "CUBRID 11.4.6 (11.4.6.1963-0e7d3c1) (64bit release build for Linux) (Sep  7 2026 17:45:11)"
)
REL_1147 = "CUBRID 11.4.7 (11.4.7.2001-1a2b3c4) (64bit release build for Linux)"
REL_1150 = "CUBRID 11.5.0 (11.5.0.0100-abcdef0) (64bit release build for Linux)"
REL_1145 = "CUBRID 11.4.5 (11.4.5.1900-0123456) (64bit release build for Linux)"


class DecisionTests(unittest.TestCase):
    def test_equal_digest_starts_no_duplicate_database(self) -> None:
        decision = latest_server.decide(REF_A, REL_1146, REF_A, REL_1146)
        self.assertEqual(decision, {"status": "same-image", "canary": "false", "image": ""})

    def test_newer_ga_series_runs_the_canary_on_the_immutable_ref(self) -> None:
        for rel in (REL_1150, REL_1147):
            with self.subTest(rel=rel):
                decision = latest_server.decide(REF_B, rel, REF_A, REL_1146)
                self.assertEqual(decision, {"status": "newer", "canary": "true", "image": REF_B})

    def test_other_digest_that_is_not_newer_runs_nothing(self) -> None:
        for rel in (REL_1145, REL_1146):
            with self.subTest(rel=rel):
                decision = latest_server.decide(REF_B, rel, REF_A, REL_1146)
                self.assertEqual(decision["status"], "not-newer")
                self.assertEqual(decision["canary"], "false")

    def test_unavailable_or_invalid_upstream_is_unverified(self) -> None:
        cases = (
            ("", "", REF_A, REL_1146),  # latest pull failed
            (REF_A, REL_1146, "", ""),  # series pull failed
            ("cubrid/cubrid:latest", REL_1146, REF_A, REL_1146),  # a tag, not a digest
            ("other/image@sha256:" + "a" * 64, REL_1146, REF_A, REL_1146),
            (REF_A + "\nREF=x", REL_1146, REF_A, REL_1146),
            (REF_B, "cubrid_rel: command not found", REF_A, REL_1146),
            (REF_B, REL_1150, REF_A, ""),
        )
        for case in cases:
            with self.subTest(case=case):
                decision = latest_server.decide(*case)
                self.assertEqual(decision, {"status": "unverified", "canary": "false", "image": ""})

    def test_report_never_claims_an_unrun_or_failed_canary(self) -> None:
        self.assertEqual(latest_server.report("newer", REF_B, "success")[0], 0)
        self.assertIn("passed", latest_server.report("newer", REF_B, "success")[1])
        for outcome in ("failure", "skipped", "cancelled", ""):
            with self.subTest(outcome=outcome):
                code, line, annotation = latest_server.report("newer", REF_B, outcome)
                self.assertEqual(code, 1)
                self.assertNotIn("passed", line)
                self.assertIn("NOT verified", line)
                self.assertTrue(annotation.startswith("::error::"))
        code, line, annotation = latest_server.report("unverified", "", "")
        self.assertEqual(code, 0)
        self.assertIn("UNVERIFIED", line)
        self.assertNotIn("passed", line)
        self.assertTrue(annotation.startswith("::warning::"))
        for status in ("same-image", "not-newer"):
            self.assertEqual(latest_server.report(status, "", "")[:2][0], 0)
        # An unknown status (for example the resolve step never ran) is unverified.
        self.assertIn("UNVERIFIED", latest_server.report("", "", "")[1])

    def test_resolve_writes_outputs_and_records_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out"
            stdout = io.StringIO()
            args = ["resolve", "--latest-ref", REF_A, "--latest-rel", REL_1146]
            args += ["--series-ref", REF_A, "--series-rel", REL_1146]
            args += ["--date", "2026-10-26", "--output", str(output)]
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(latest_server.main(args), 0)
            self.assertEqual(output.read_text(), "status=same-image\ncanary=false\nimage=\n")
        text = stdout.getvalue()
        for evidence in (REF_A, "11.4.6.1963", "2026-10-26", "No extra database started"):
            self.assertIn(evidence, text)
        # The equal-digest wording ties any claim to the digest the cells record
        # (#480 rule 4); it never claims the cells passed or are the newest test.
        self.assertIn(f"the newest-stable image is `{REF_A}`", text)
        self.assertIn("only if they show this same digest", text)
        self.assertNotIn("are the newest-stable test", text)
        self.assertNotIn("passed", text)

    def test_report_appends_to_the_summary_and_fails_a_failed_canary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary"
            stdout = io.StringIO()
            args = ["report", "--status", "newer", "--image", REF_B, "--outcome", "failure"]
            with contextlib.redirect_stdout(stdout):
                code = latest_server.main([*args, "--summary", str(summary)])
            self.assertEqual(code, 1)
            self.assertIn("NOT verified", summary.read_text())
            self.assertNotIn("::error::", summary.read_text())
            self.assertTrue(stdout.getvalue().startswith("::error::"))


class WorkflowTests(unittest.TestCase):
    def job(self) -> str:
        return "\n".join(parse_jobs(SMOKE)["latest-server"])

    def test_runs_only_weekly_or_on_a_manual_full_smoke(self) -> None:
        condition = " ".join(
            self.job().split("    if: >-\n", 1)[1].split("\n    runs-on:")[0].split()
        )
        self.assertEqual(
            condition,
            "${{ !inputs.package && github.event_name == 'schedule' && github.event.schedule"
            " == '0 0 * * 1' || github.event_name == 'workflow_dispatch'"
            " && inputs.package == 'latest' }}",
        )

    def test_is_advisory_and_outside_the_release_report(self) -> None:
        job = self.job()
        self.assertIn("    continue-on-error: true\n", job)
        self.assertNotIn("needs:", job)
        report = "\n".join(parse_jobs(SMOKE)["report"])
        self.assertIn("    needs: verify\n", report)
        self.assertNotIn("latest-server", report)
        self.assertNotIn("secrets.", job)
        self.assertNotIn("permissions:", job)  # inherits the read-only workflow token

    def test_resolves_once_and_tests_the_immutable_reference(self) -> None:
        job = self.job()
        self.assertEqual(job.count("docker pull"), 1)
        self.assertIn("for tag in latest 11.4; do", job)
        self.assertIn("--entrypoint bash", job)
        self.assertIn("cubrid_rel", job)
        self.assertIn("python3 scripts/latest_server.py resolve", job)
        self.assertIn("if: steps.resolve.outputs.canary == 'true'", job)
        self.assertIn('"$CANARY_IMAGE"', job)
        self.assertIn("CANARY_IMAGE: ${{ steps.resolve.outputs.image }}", job)
        self.assertNotIn("cubrid/cubrid:latest\n", job.replace('"cubrid/cubrid:$tag"', ""))
        self.assertIn("SELECT VERSION()", job)
        self.assertIn("make verify-goldens VERIFY_PATHS=fundamentals/pycubrid", job)
        final = job.split("      - name: Report newest CUBRID image result\n", 1)[1]
        self.assertIn("if: always()", final)
        self.assertIn("CANARY_OUTCOME: ${{ steps.canary.outcome }}", final)
        self.assertIn("python3 scripts/latest_server.py report", final)

    def test_every_smoke_cell_records_the_image_it_ran(self) -> None:
        verify = SMOKE[SMOKE.index("\n  verify:") : SMOKE.index("\n  report:")]
        start = verify.index("      - name: Start CUBRID containers\n")
        record = verify.index("      - name: Record CUBRID image\n")
        setup = verify.index("      - name: Setup Python\n")
        self.assertLess(start, record)
        self.assertLess(record, setup)
        step = verify[record:setup]
        self.assertIn("CUBRID_IMAGE: cubrid/cubrid:${{ matrix.cubrid }}", step)
        self.assertIn("{{index .RepoDigests 0}}", step)
        self.assertIn("docker exec cubrid bash -lc cubrid_rel", step)
        self.assertIn('tee -a "$GITHUB_STEP_SUMMARY"', step)
        self.assertNotIn("if:", step)  # every event, including release runs
        self.assertNotIn("inputs.", step)

    def test_never_touches_support_or_release_files(self) -> None:
        job = self.job()
        for forbidden in ("SUPPORT_MATRIX", "RELEASE_CELLS", "release_smoke", "upload-artifact"):
            self.assertNotIn(forbidden, job)


if __name__ == "__main__":
    unittest.main()
