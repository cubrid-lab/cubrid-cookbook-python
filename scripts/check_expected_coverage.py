#!/usr/bin/env python3
"""check_expected_coverage.py - Guard against silently-unverified examples.

`make verify` is golden-driven: it discovers `*/expected/*.expected` files and
runs the sibling `<name>.py`. A consequence is that any example script WITHOUT a
matching `.expected` golden is never executed in CI -- it can rot, break, or even
crash and nobody notices (see issue #89).

This guard closes that gap. For every directory that OWNS an `expected/`
subdirectory (i.e. it has opted in to golden verification), every runnable
sibling `*.py` MUST either:

  1. have a matching `expected/<stem>.expected` golden, OR
  2. be listed in the exclusions allowlist with a human-readable reason.

Runnable scripts exclude dunder/private helpers (`__init__.py`, `_*.py`).

Usage:
    python scripts/check_expected_coverage.py            # scan repo root
    python scripts/check_expected_coverage.py PATH ...   # scan specific roots

Exit code 0 when every opted-in script is covered; 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH = REPO_ROOT / "scripts" / "verify_exclusions.txt"


def load_allowlist() -> set[str]:
    """Return repo-relative script paths that are intentionally un-goldened.

    Format: one path per line; `#` starts a comment. A reason is REQUIRED as a
    trailing comment so exclusions are auditable, e.g.:

        fundamentals/foo/99_interactive.py  # needs TTY input, not reproducible

    Raises ValueError on an entry that has a path but no trailing reason.
    """
    allow: set[str] = set()
    if not ALLOWLIST_PATH.exists():
        return allow
    for lineno, raw in enumerate(ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        path_part, sep, reason = line.partition("#")
        path_part = path_part.strip()
        if not path_part:
            continue
        if not sep or not reason.strip():
            raise ValueError(
                f"{ALLOWLIST_PATH.name}:{lineno}: exclusion '{path_part}' needs a "
                "trailing '# reason' comment explaining why it has no golden"
            )
        allow.add(path_part)
    return allow


def is_runnable_example(py: Path) -> bool:
    name = py.name
    if name == "__init__.py":
        return False
    if name.startswith("_"):
        return False
    return True


def find_missing(roots: list[Path], allowlist: set[str]) -> list[str]:
    missing: list[str] = []
    for root in roots:
        for expected_dir in sorted(root.rglob("expected")):
            if not expected_dir.is_dir():
                continue
            example_dir = expected_dir.parent
            for py in sorted(example_dir.glob("*.py")):
                if not is_runnable_example(py):
                    continue
                rel = py.relative_to(REPO_ROOT).as_posix()
                if rel in allowlist:
                    continue
                golden = expected_dir / f"{py.stem}.expected"
                if not golden.exists():
                    missing.append(rel)
    return missing


def main(argv: list[str]) -> int:
    if argv:
        roots = [Path(a).resolve() for a in argv]
    else:
        roots = [REPO_ROOT]

    try:
        allowlist = load_allowlist()
    except ValueError as exc:
        print(f"Invalid exclusions allowlist: {exc}")
        return 1
    missing = find_missing(roots, allowlist)

    if missing:
        print("Missing .expected goldens for opted-in example scripts:\n")
        for rel in missing:
            print(f"  ✗ {rel}")
        print(
            "\nEvery *.py in a directory that owns an expected/ folder must have a\n"
            f"matching expected/<name>.expected golden, or be listed in\n"
            f"{ALLOWLIST_PATH.relative_to(REPO_ROOT).as_posix()} with a reason.\n"
            "\nGenerate a golden with:\n"
            "  set -o pipefail; python3 <script>.py 2>&1 \\\n"
            "    | bash scripts/normalize_output.sh > <dir>/expected/<name>.expected"
        )
        return 1

    print("All opted-in example scripts have matching .expected goldens.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
