"""Unit tests for scripts/mcp_smoke.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
