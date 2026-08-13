#!/usr/bin/env python3
"""Fail CI when an example directory drifts out of sync with the docs.

This gate enforces the "code without doc updates is incomplete" rule from the
4-phase Development Workflow in AGENTS.md / CONTRIBUTING.md. It catches the exact
class of drift fixed in issue #42, where example directories existed on disk but
were never listed in README.md and never smoke-tested.

Two checks are performed for every example directory (an immediate subdirectory
of one of the category roots):

1. README reference (BLOCKING): the example's ``<category>/<name>`` path must
   appear somewhere in README.md. A missing reference fails the gate.
2. Smoke coverage (WARNING): the example should ship an ``expected/`` directory
   (``make verify`` golden files) or a ``tests/`` directory (pytest). Examples
   without either are reported as warnings and do not fail the gate, so the
   existing coverage backlog can be paid down incrementally. Intentional
   exceptions are listed in ``scripts/docs-sync-allowlist.txt``.

Run ``python3 scripts/check_docs_sync.py`` from the repository root.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Category roots whose immediate subdirectories are individual examples.
# ``pitfalls`` is intentionally excluded: it is a single README, not a set of
# example subdirectories.
CATEGORY_ROOTS = (
    "quickstart",
    "migration",
    "templates",
    "performance",
    "fundamentals",
)

# Directory names that are never examples even when they sit under a category root.
_IGNORED_DIRS = {"__pycache__", ".pytest_cache", "expected", "tests"}


def discover_examples(repo_root: Path) -> list[str]:
    """Return sorted ``<category>/<name>`` example paths present on disk.

    Only immediate subdirectories of each category root are treated as examples;
    nested recipe folders (for example ``templates/flask/01-basic-crud``) are not.
    """
    examples: list[str] = []
    for category in CATEGORY_ROOTS:
        category_dir = repo_root / category
        if not category_dir.is_dir():
            continue
        for child in sorted(category_dir.iterdir()):
            if child.is_dir() and child.name not in _IGNORED_DIRS:
                examples.append(f"{category}/{child.name}")
    return examples


def load_allowlist(allowlist_path: Path) -> set[str]:
    """Parse an allowlist file into a set of exempt example paths.

    Blank lines and ``#`` comments are ignored; an inline ``#`` comment on an
    entry line is stripped so a reason can be recorded next to each path.

    >>> import tempfile, os
    >>> f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    >>> _ = f.write("# reason header\\n\\nperformance/bulk-insert  # benchmark only\\n")
    >>> f.close()
    >>> sorted(load_allowlist(Path(f.name)))
    ['performance/bulk-insert']
    >>> os.unlink(f.name)
    >>> load_allowlist(Path("/does/not/exist.txt"))
    set()
    """
    if not allowlist_path.is_file():
        return set()
    entries: set[str] = set()
    for raw in allowlist_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            entries.add(line)
    return entries


def find_undocumented(examples: list[str], readme_text: str) -> list[str]:
    """Return examples whose path string is absent from the README text.

    >>> find_undocumented(
    ...     ["templates/flask", "templates/django"],
    ...     "see templates/flask for details",
    ... )
    ['templates/django']
    >>> find_undocumented([], "anything")
    []
    """
    return [ex for ex in examples if ex not in readme_text]


def find_untested(repo_root: Path, examples: list[str], allowlist: set[str]) -> list[str]:
    """Return non-allowlisted examples lacking an ``expected/`` or ``tests/`` dir."""
    untested: list[str] = []
    for ex in examples:
        if ex in allowlist:
            continue
        example_dir = repo_root / ex
        has_expected = any(example_dir.rglob("expected"))
        has_tests = any(example_dir.rglob("tests"))
        if not has_expected and not has_tests:
            untested.append(ex)
    return untested


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    readme_text = (repo_root / "README.md").read_text(encoding="utf-8")
    allowlist = load_allowlist(repo_root / "scripts" / "docs-sync-allowlist.txt")

    examples = discover_examples(repo_root)
    undocumented = find_undocumented(examples, readme_text)
    untested = find_untested(repo_root, examples, allowlist)

    print(f"Scanned {len(examples)} example directories across {len(CATEGORY_ROOTS)} categories.")

    if untested:
        print("\nWARN: examples without smoke coverage (expected/ or tests/):")
        for ex in untested:
            print(f"  - {ex}")
        print("  Add golden files, a pytest suite, or an allowlist entry with a reason.")

    if undocumented:
        print("\nERROR: examples missing from README.md:")
        for ex in undocumented:
            print(f"  - {ex}")
        print("\nDocument each example in README.md (Project Structure and the relevant table).")
        print("This gate enforces the 4-phase workflow: code without doc updates is incomplete.")
        return 1

    print("\nOK: every example directory is referenced in README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
