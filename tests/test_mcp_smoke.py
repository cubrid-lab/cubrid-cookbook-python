"""Unit tests for scripts/mcp_smoke.py."""

from __future__ import annotations

import contextlib
import io
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import mcp_smoke  # noqa: E402


class NumericReleaseTests(unittest.TestCase):
    def test_plain_version(self):
        self.assertEqual(mcp_smoke._numeric_release("0.4.0"), (0, 4, 0))

    def test_short_version_is_padded_with_zeros(self):
        self.assertEqual(mcp_smoke._numeric_release("1.2"), (1, 2, 0))
        self.assertEqual(mcp_smoke._numeric_release("1"), (1, 0, 0))

    def test_prerelease_suffix_is_ignored(self):
        self.assertEqual(mcp_smoke._numeric_release("0.4.0rc1"), (0, 4, 0))

    def test_extra_components_are_dropped(self):
        self.assertEqual(mcp_smoke._numeric_release("1.2.3.4"), (1, 2, 3))

    def test_empty_or_non_numeric_version_is_all_zeros(self):
        self.assertEqual(mcp_smoke._numeric_release(""), (0, 0, 0))
        self.assertEqual(mcp_smoke._numeric_release("dev"), (0, 0, 0))


class HealthCheckGateTests(unittest.TestCase):
    def test_floor_release_is_not_newer_and_next_patch_is(self):
        # main() requires health_check when the installed release is strictly
        # newer than (0, 2, 1), so both sides of that comparison are pinned.
        self.assertFalse(mcp_smoke._numeric_release("0.2.1") > (0, 2, 1))
        self.assertTrue(mcp_smoke._numeric_release("0.2.2") > (0, 2, 1))


class MainTests(unittest.TestCase):
    """Cover the tool-contract checks in mcp_smoke.main().

    main() imports cubrid_mcp_server.server inside the function and the package is
    not installed by ``make deps``, so each test injects fake modules into
    sys.modules. patch.dict restores sys.modules when the test finishes.
    """

    @staticmethod
    def _fake_modules(tool_names):
        async def list_tools():
            return [types.SimpleNamespace(name=name) for name in tool_names]

        server = types.ModuleType("cubrid_mcp_server.server")
        server.mcp = types.SimpleNamespace(list_tools=list_tools)
        package = types.ModuleType("cubrid_mcp_server")
        package.server = server
        return {"cubrid_mcp_server": package, "cubrid_mcp_server.server": server}

    def _run_main(self, tool_names, release):
        """Run main() against fake tools and a fake installed release; return stdout."""
        output = io.StringIO()
        with (
            mock.patch.dict(sys.modules, self._fake_modules(tool_names)),
            mock.patch.object(mcp_smoke, "_pkg_version", return_value=release),
            contextlib.redirect_stdout(output),
        ):
            mcp_smoke.main()
        return output.getvalue()

    def test_full_contract_with_health_check_passes(self):
        names = mcp_smoke.EXPECTED | mcp_smoke.OPTIONAL

        output = self._run_main(names, "0.4.0")

        self.assertIn("real-usage smoke OK", output)
        self.assertIn("requiring health_check", output)

    def test_missing_expected_tool_exits_naming_it(self):
        names = (mcp_smoke.EXPECTED | mcp_smoke.OPTIONAL) - {"execute_query"}

        with self.assertRaises(SystemExit) as raised:
            self._run_main(names, "0.4.0")

        self.assertIn("missing expected tools", str(raised.exception.code))
        self.assertIn("execute_query", str(raised.exception.code))

    def test_undocumented_tool_exits_naming_it(self):
        names = mcp_smoke.EXPECTED | mcp_smoke.OPTIONAL | {"drop_all_tables"}

        with self.assertRaises(SystemExit) as raised:
            self._run_main(names, "0.4.0")

        self.assertIn("undocumented tools", str(raised.exception.code))
        self.assertIn("drop_all_tables", str(raised.exception.code))

    def test_floor_release_without_health_check_passes(self):
        output = self._run_main(set(mcp_smoke.EXPECTED), "0.2.1")

        self.assertIn("real-usage smoke OK", output)
        self.assertNotIn("requiring health_check", output)

    def test_floor_release_tolerates_optional_health_check(self):
        names = mcp_smoke.EXPECTED | mcp_smoke.OPTIONAL

        output = self._run_main(names, "0.2.1")

        self.assertIn("real-usage smoke OK", output)

    def test_release_newer_than_floor_without_health_check_exits(self):
        with self.assertRaises(SystemExit) as raised:
            self._run_main(set(mcp_smoke.EXPECTED), "0.2.2")

        self.assertIn("missing expected tools", str(raised.exception.code))
        self.assertIn("health_check", str(raised.exception.code))

    def test_fake_modules_are_removed_after_the_run(self):
        self._run_main(mcp_smoke.EXPECTED | mcp_smoke.OPTIONAL, "0.4.0")

        self.assertNotIn("cubrid_mcp_server", sys.modules)
        self.assertNotIn("cubrid_mcp_server.server", sys.modules)


if __name__ == "__main__":
    unittest.main()
