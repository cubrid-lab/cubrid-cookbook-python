#!/usr/bin/env python3
"""example_requirements.py - Find the requirements of golden-backed examples.

A golden-backed example is a directory that owns an ``expected/`` folder (the
same opt-in that ``make verify`` and ``scripts/check_expected_coverage.py``
use). Hidden directories such as ``.git`` or ``.venv`` are never searched.

Shared by ``make deps`` (one pip resolver call over every file) and
``scripts/release_smoke.py install-examples`` (CI).

Usage:
    python scripts/example_requirements.py [ROOT ...]          # print the files
                                                              # (fails on a path with whitespace)
    python scripts/example_requirements.py --check [ROOT ...]  # verify pre-flight

``--check`` fails once, listing every requirement whose distribution is not
installed, with a hint to run ``make deps``. It checks presence only, not
versions or extras.
"""

from __future__ import annotations

import os
import re
import sys
from importlib import metadata
from pathlib import Path

REQUIREMENT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def requirement_files(root: Path) -> list[Path]:
    """Return ``requirements.txt`` of every golden-backed example under ``root``."""
    found = []
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = sorted(d for d in subdirectories if not d.startswith("."))
        if "expected" in subdirectories and "requirements.txt" in files:
            found.append(Path(directory) / "requirements.txt")
    return sorted(found)


def requirement_names(requirements: Path) -> list[str]:
    """Return the distribution names a requirements file lists (no options or includes)."""
    names = []
    for line in requirements.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        match = REQUIREMENT_NAME.match(line)
        if match:
            names.append(match.group())
    return names


def missing_distributions(roots: list[Path]) -> list[str]:
    missing = []
    for root in roots:
        for requirements in requirement_files(root):
            for name in requirement_names(requirements):
                try:
                    metadata.distribution(name)
                except metadata.PackageNotFoundError:
                    missing.append(f"{name} ({requirements.as_posix()})")
    return sorted(set(missing))


def main(argv: list[str]) -> int:
    check = argv[:1] == ["--check"]
    roots = [Path(arg) for arg in (argv[1:] if check else argv)] or [Path(".")]
    if check:
        missing = missing_distributions(roots)
        if missing:
            print("Missing example dependencies: run `make deps` first.", file=sys.stderr)
            for entry in missing:
                print(f"  ✗ {entry}", file=sys.stderr)
            return 1
        return 0
    files = [path.as_posix() for root in roots for path in requirement_files(root)]
    # `make deps` splits this output on whitespace, so reject such a path
    # before printing anything rather than emit a partial list.
    spaced = [path for path in files if any(character.isspace() for character in path)]
    if spaced:
        for path in spaced:
            print(f"Requirements path contains whitespace: {path!r}", file=sys.stderr)
        return 1
    for path in files:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
