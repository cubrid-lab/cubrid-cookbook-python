#!/usr/bin/env python3
"""example_requirements.py - Find the requirements of golden-backed examples.

A golden-backed example is a directory that owns an ``expected/`` folder (the
same opt-in that ``make verify-goldens`` and ``scripts/check_expected_coverage.py``
use). Hidden directories such as ``.git`` or ``.venv`` are never searched.
``--all`` selects every example ``requirements.txt`` instead: the golden-backed
ones plus those of the pytest suites that a full ``make verify`` runs.

Shared by ``make deps`` (``--all``; one pip resolver call over every file),
``make verify`` (``--check``) and ``scripts/release_smoke.py install-examples`` (CI,
golden-backed only).

Usage:
    python scripts/example_requirements.py [--all] [ROOT ...]          # print the files
                                                                      # (fails on a path with whitespace)
    python scripts/example_requirements.py --check [--all] [ROOT ...]  # verify pre-flight

``--check`` fails once, listing every requirement whose distribution is not
installed and applies in the current environment, with a hint to run ``make deps``.
It checks presence only, not versions or extras. Checking requires ``packaging``
(installed with pytest by ``make deps``); file discovery uses only the standard
library. Pip options and includes are skipped, not recursively resolved.
"""

from __future__ import annotations

import os
import re
import sys
from importlib import metadata
from pathlib import Path


def requirement_files(root: Path, every: bool = False) -> list[Path]:
    """Return ``requirements.txt`` of every golden-backed (or, with ``every``, any) example."""
    found = []
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = sorted(d for d in subdirectories if not d.startswith("."))
        if (every or "expected" in subdirectories) and "requirements.txt" in files:
            found.append(Path(directory) / "requirements.txt")
    return sorted(found)


def requirement_names(requirements: Path) -> list[str]:
    """Return applicable PEP 508 distribution names (no pip options or includes)."""
    # Keep file discovery usable before make deps installs the checking tools.
    try:
        from packaging.markers import UndefinedComparison, UndefinedEnvironmentName
        from packaging.requirements import InvalidRequirement, Requirement
    except ImportError as exc:
        raise ValueError(
            "Dependency preflight needs 'packaging'; install it with `python -m pip install packaging`"
        ) from exc

    names = []
    for number, line in enumerate(requirements.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        # Inline comments require whitespace; preserve direct-URL hash fragments
        # so a later environment marker still reaches the PEP 508 parser.
        line = re.split(r"\s+#", line, maxsplit=1)[0].strip()
        try:
            requirement = Requirement(line)
            if requirement.marker is None or requirement.marker.evaluate():
                names.append(requirement.name)
        except (InvalidRequirement, UndefinedComparison, UndefinedEnvironmentName) as exc:
            raise ValueError(
                f"{requirements}:{number}: unsupported requirement {line!r}: {exc}"
            ) from exc
    return names


# Test tools the live suites import but no example requirements.txt lists;
# `make deps` installs them next to the requirement files.
SUITE_TOOLS = ("pytest", "pytest-asyncio")


def missing_distributions(roots: list[Path], every: bool = False) -> list[str]:
    missing = []
    for name in SUITE_TOOLS if every else ():
        try:
            metadata.distribution(name)
        except metadata.PackageNotFoundError:
            missing.append(f"{name} (live pytest suites)")
    for root in roots:
        for requirements in requirement_files(root, every):
            for name in requirement_names(requirements):
                try:
                    metadata.distribution(name)
                except metadata.PackageNotFoundError:
                    missing.append(f"{name} ({requirements.as_posix()})")
    return sorted(set(missing))


def main(argv: list[str]) -> int:
    check = "--check" in argv
    every = "--all" in argv
    roots = [Path(arg) for arg in argv if arg not in ("--check", "--all")] or [Path(".")]
    if check:
        try:
            missing = missing_distributions(roots, every)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if missing:
            print("Missing example dependencies: run `make deps` first.", file=sys.stderr)
            for entry in missing:
                print(f"  ✗ {entry}", file=sys.stderr)
            return 1
        return 0
    files = [path.as_posix() for root in roots for path in requirement_files(root, every)]
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
