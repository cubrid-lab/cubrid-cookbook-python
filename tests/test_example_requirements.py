"""Unit tests for scripts/example_requirements.py."""

from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import unittest
from importlib import metadata
from pathlib import Path
from unittest import mock

from packaging.markers import default_environment

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import example_requirements  # noqa: E402


class RequirementNamesTests(unittest.TestCase):
    def test_requirement_names_skips_comments_options_and_normalizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_file = Path(tmp) / "requirements.txt"
            content = (
                "# top\n"
                "pytest>=8  # c\n"
                "\n"
                "-r base.txt\n"
                "sqlalchemy-cubrid[pycubrid]==1\n"
                "  Foo_bar.baz ; python_version<'3.12'\n"
            )
            req_file.write_text(content, encoding="utf-8")
            with mock.patch(
                "packaging.markers.default_environment",
                return_value={**default_environment(), "python_version": "3.11"},
            ):
                names = example_requirements.requirement_names(req_file)
            self.assertEqual(names, ["pytest", "sqlalchemy-cubrid", "Foo_bar.baz"])

    def test_empty_requirements_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_file = Path(tmp) / "requirements.txt"
            req_file.write_text("# only comments\n\n", encoding="utf-8")
            self.assertEqual(example_requirements.requirement_names(req_file), [])

    def test_direct_url_fragment_does_not_hide_its_environment_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_file = Path(tmp) / "requirements.txt"
            req_file.write_text(
                "active @ https://example.test/a.whl#sha256=abc ; python_version >= '3.12'\n"
                "inactive @ https://example.test/b.whl#sha256=def ; python_version < '3.12'\n",
                encoding="utf-8",
            )
            with mock.patch(
                "packaging.markers.default_environment",
                return_value={**default_environment(), "python_version": "3.12"},
            ):
                self.assertEqual(example_requirements.requirement_names(req_file), ["active"])

    def test_invalid_requirement_has_file_and_line_diagnostic(self):
        for invalid in (
            "broken requirement !!!",
            "broken; python_version >> '3.12'",
            "https://example.test/unnamed.whl",
        ):
            with self.subTest(requirement=invalid), tempfile.TemporaryDirectory() as tmp:
                req_file = Path(tmp) / "requirements.txt"
                req_file.write_text(f"# comment\n{invalid}\n", encoding="utf-8")
                with self.assertRaises(ValueError) as caught:
                    example_requirements.requirement_names(req_file)
                self.assertIn(f"{req_file}:2:", str(caught.exception))
                self.assertIn("unsupported requirement", str(caught.exception))


class MissingDistributionsTests(unittest.TestCase):
    def test_preflight_checks_only_requirements_active_in_current_environment(self):
        cases = (
            ("3.11", "linux", {"legacy-pkg", "plain-pkg"}),
            ("3.12", "linux", {"modern-linux-pkg", "plain-pkg"}),
            ("3.12", "win32", {"windows-pkg", "plain-pkg"}),
        )
        for version, platform, expected in cases:
            with self.subTest(version=version, platform=platform):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "expected").mkdir()
                    req_file = root / "requirements.txt"
                    req_file.write_text(
                        "legacy-pkg ; python_version < '3.12'\n"
                        "windows-pkg ; sys_platform == 'win32'\n"
                        "modern-linux-pkg ; python_version >= '3.12' and sys_platform == 'linux'\n"
                        "plain-pkg[optional]>=999  # presence only, not version resolution\n",
                        encoding="utf-8",
                    )
                    with (
                        mock.patch(
                            "packaging.markers.default_environment",
                            return_value={
                                **default_environment(),
                                "python_version": version,
                                "python_full_version": f"{version}.0",
                                "sys_platform": platform,
                            },
                        ),
                        mock.patch.object(
                            example_requirements.metadata,
                            "distribution",
                            side_effect=metadata.PackageNotFoundError("not installed"),
                        ) as lookup,
                    ):
                        missing = example_requirements.missing_distributions([root])
                    self.assertEqual({call.args[0] for call in lookup.call_args_list}, expected)
                    self.assertEqual(
                        missing, sorted(f"{name} ({req_file.as_posix()})" for name in expected)
                    )

    def test_missing_distributions_reports_uninstalled_packages_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            golden = root / "example"
            golden.mkdir()
            (golden / "expected").mkdir()
            req_file = golden / "requirements.txt"
            req_file.write_text(
                "installed-pkg>=1.0\nmissing-pkg==2.0\n",
                encoding="utf-8",
            )

            def fake_distribution(name: str):
                if name == "installed-pkg":
                    return mock.MagicMock()
                raise metadata.PackageNotFoundError(name)

            with mock.patch.object(
                example_requirements.metadata, "distribution", side_effect=fake_distribution
            ):
                missing = example_requirements.missing_distributions([root])

            expected_path = req_file.as_posix()
            self.assertEqual(missing, [f"missing-pkg ({expected_path})"])

    def test_missing_distributions_deduplicates_repeated_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            golden = root / "example"
            golden.mkdir()
            (golden / "expected").mkdir()
            req_file = golden / "requirements.txt"
            req_file.write_text("pkg\npkg\n", encoding="utf-8")

            with mock.patch.object(
                example_requirements.metadata,
                "distribution",
                side_effect=metadata.PackageNotFoundError("pkg"),
            ):
                missing = example_requirements.missing_distributions([root])

            self.assertEqual(len(missing), 1)
            self.assertEqual(missing, [f"pkg ({req_file.as_posix()})"])

    def test_all_examples_also_require_the_suite_test_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite = root / "templates" / "app"
            suite.mkdir(parents=True)
            req_file = suite / "requirements.txt"
            req_file.write_text("framework\n", encoding="utf-8")

            def fake_distribution(name: str):
                if name == "pytest":
                    return mock.MagicMock()
                raise metadata.PackageNotFoundError(name)

            with mock.patch.object(
                example_requirements.metadata, "distribution", side_effect=fake_distribution
            ):
                golden_only = example_requirements.missing_distributions([root])
                every = example_requirements.missing_distributions([root], every=True)

            self.assertEqual(golden_only, [])
            self.assertEqual(
                every,
                [f"framework ({req_file.as_posix()})", "pytest-asyncio (live pytest suites)"],
            )


class MainCheckTests(unittest.TestCase):
    def test_main_reports_invalid_requirement_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "expected").mkdir()
            req_file = root / "requirements.txt"
            req_file.write_text("not a valid requirement\n", encoding="utf-8")
            with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
                self.assertEqual(example_requirements.main(["--check", str(root)]), 1)
            self.assertIn(f"{req_file}:1: unsupported requirement", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_main_check_returns_one_and_reports_missing_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            golden = root / "example"
            golden.mkdir()
            (golden / "expected").mkdir()
            (golden / "requirements.txt").write_text("missing-lib\n", encoding="utf-8")

            with (
                mock.patch.object(
                    example_requirements.metadata,
                    "distribution",
                    side_effect=metadata.PackageNotFoundError("missing-lib"),
                ),
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = example_requirements.main(["--check", str(root)])

            self.assertEqual(exit_code, 1)
            err_output = stderr.getvalue()
            self.assertIn("Missing example dependencies: run `make deps` first.", err_output)
            self.assertIn("✗ missing-lib", err_output)

    def test_main_check_returns_zero_when_dependencies_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            golden = root / "example"
            golden.mkdir()
            (golden / "expected").mkdir()
            (golden / "requirements.txt").write_text("present-lib\n", encoding="utf-8")

            with (
                mock.patch.object(
                    example_requirements.metadata,
                    "distribution",
                    return_value=mock.MagicMock(),
                ),
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = example_requirements.main(["--check", str(root)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")

    def test_main_check_returns_zero_for_empty_or_non_golden_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(example_requirements.main(["--check", tmp]), 0)


class MainListingTests(unittest.TestCase):
    def test_listing_works_without_site_packages(self):
        # make deps must discover files before it installs the checking tools.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            req_file = self._example(root, "example", golden=True)
            result = subprocess.run(
                [sys.executable, "-S", str(ROOT / "scripts/example_requirements.py"), str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, f"{req_file.as_posix()}\n")

    @staticmethod
    def _example(root: Path, name: str, golden: bool) -> Path:
        directory = root / name
        directory.mkdir()
        if golden:
            (directory / "expected").mkdir()
        requirements = directory / "requirements.txt"
        requirements.write_text("lib\n", encoding="utf-8")
        return requirements

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        with (
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            exit_code = example_requirements.main(argv)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_main_lists_only_golden_backed_requirements_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            second = self._example(root, "b", golden=True)
            first = self._example(root, "a", golden=True)
            self._example(root, "c", golden=False)

            exit_code, out, err = self._run([str(root)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(out, f"{first.as_posix()}\n{second.as_posix()}\n")
            self.assertEqual(err, "")

    def test_main_all_lists_every_example_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            golden = self._example(root, "a", golden=True)
            plain = self._example(root, "b", golden=False)

            exit_code, out, err = self._run(["--all", str(root)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(out, f"{golden.as_posix()}\n{plain.as_posix()}\n")
            self.assertEqual(err, "")

    def test_main_never_walks_hidden_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            visible = self._example(root, "a", golden=True)
            self._example(root, ".hidden", golden=True)

            for argv in ([str(root)], ["--all", str(root)]):
                with self.subTest(argv=argv[:-1]):
                    exit_code, out, err = self._run(argv)

                    self.assertEqual(exit_code, 0)
                    self.assertEqual(out, f"{visible.as_posix()}\n")
                    self.assertNotIn(".hidden", out)
                    self.assertEqual(err, "")

    def test_main_rejects_whitespace_path_without_partial_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._example(root, "a", golden=True)
            spaced = self._example(root, "sp ace", golden=True)

            exit_code, out, err = self._run([str(root)])

            self.assertEqual(exit_code, 1)
            self.assertEqual(out, "")
            self.assertEqual(err, f"Requirements path contains whitespace: {spaced.as_posix()!r}\n")


if __name__ == "__main__":
    unittest.main()
