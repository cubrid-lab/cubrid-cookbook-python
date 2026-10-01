#!/usr/bin/env python3
"""check_dependency_floors.py - Keep recipe driver floors honest (#152).

``SUPPORT_MATRIX.md``'s "Driver & Framework Versions" table is the single
documented support contract for the cookbook's minimum ``pycubrid`` and
``sqlalchemy-cubrid`` versions. Every standalone recipe/template
``requirements.txt`` must either:

* pin the driver at (or above) that global floor, with no upper bound, or
* belong to one of the documented per-recipe/per-family exceptions below,
  each of which mirrors a paragraph in ``SUPPORT_MATRIX.md`` explaining why
  that directory pins a different floor.

A bare, unversioned ``pycubrid``/``sqlalchemy-cubrid`` line is always an
error: every recipe here is installed standalone (``pip install -r
requirements.txt`` in its own directory, per its README), so an unbounded
driver requirement can silently resolve to a release far below anything this
cookbook has ever run against.

Usage:
    python scripts/check_dependency_floors.py

Exit code 0 when every requirements file matches the documented contract;
1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = REPO_ROOT / "SUPPORT_MATRIX.md"

DRIVERS = ("pycubrid", "sqlalchemy-cubrid")
REQ_LINE_RE = re.compile(r"^(pycubrid|sqlalchemy-cubrid)(.*)$")
FLOOR_RE = re.compile(r"^>=([0-9][\w.]*?)(,<[0-9][\w.]*)?$")

# The full example apps under templates/ (and their standalone per-recipe
# requirements.txt) install pycubrid from a pinned recent range rather than
# the bare global floor -- see the "full example apps under templates/"
# paragraph in SUPPORT_MATRIX.md.
TEMPLATE_PYCUBRID_GLOBS = (
    "fundamentals/connect",
    "fundamentals/orm-basics",
    "templates/flask",
    "templates/flask/*",
    "templates/api-service-fastapi",
    "templates/api-service-fastapi/recipes/*",
    "templates/ai-agent",
    "templates/async-worker",
    "templates/batch-etl",
)
TEMPLATE_PYCUBRID_FLOOR = "1.7,<2"

# Only the flask family (template + recipes) also raises the
# sqlalchemy-cubrid floor to match; api-service-fastapi keeps the global 1.0
# (its recipes use no async/ORM feature that needs more).
TEMPLATE_SQLALCHEMY_GLOBS = (
    "fundamentals/orm-basics",
    "templates/flask",
    "templates/flask/*",
    "templates/ai-agent",
    "templates/async-worker",
    "templates/batch-etl",
)
TEMPLATE_SQLALCHEMY_FLOOR = "1.7,<2"

# fundamentals/pycubrid's 16_batch_error_handling and 20_timezone_datetime
# goldens assume the errno-carrying batch errors (#390) and the CAS session
# kept across commit() (#468/#472) that first shipped in pycubrid 1.8.0.
EXACT_PYCUBRID_FLOOR = {
    "fundamentals/pycubrid": "1.8,<2",
}

# "Advanced" SQLAlchemy recipes are pinned to the floor documented in the
# [^async] footnote (sqlalchemy-cubrid 1.2.3 first shipped the async dialect
# entry points; this cookbook pins 1.4.2 to match every advanced recipe).
ADVANCED_SQLALCHEMY_DIRS = (
    "fundamentals/async",
    "fundamentals/pandas",
    "fundamentals/sqlalchemy",
    "templates/dashboard",
    "templates/django",
)
ADVANCED_SQLALCHEMY_FLOOR = "1.4.2"


def _requirement_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*requirements*.txt") if p.is_file())


def _global_floors(matrix: str) -> dict[str, str]:
    floors: dict[str, str] = {}
    for driver in DRIVERS:
        match = re.search(rf"\|\s*{re.escape(driver)}\s*\|\s*≥\s*([0-9][\w.]*)\s*\|", matrix)
        if match:
            floors[driver] = match.group(1)
    return floors


def _expand(root: Path, globs: tuple[str, ...]) -> set[str]:
    resolved: set[str] = set()
    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            if path.is_dir():
                resolved.add(path.relative_to(root).as_posix())
    return resolved


def check(root: Path, matrix: str) -> list[str]:
    errors: list[str] = []
    global_floors = _global_floors(matrix)
    for driver in DRIVERS:
        if driver not in global_floors:
            errors.append(f"SUPPORT_MATRIX.md: no global floor found for {driver!r}")
    if errors:
        return errors

    template_pycubrid_dirs = _expand(root, TEMPLATE_PYCUBRID_GLOBS)
    template_sqlalchemy_dirs = _expand(root, TEMPLATE_SQLALCHEMY_GLOBS)

    for req_file in _requirement_files(root):
        directory = req_file.parent.relative_to(root).as_posix()
        for line in req_file.read_text(encoding="utf-8").splitlines():
            match = REQ_LINE_RE.match(line.strip())
            if not match:
                continue
            driver, rest = match.groups()
            where = f"{req_file.relative_to(root)}: {line.strip()!r}"
            if not rest:
                errors.append(f"{where}: no version floor (every recipe installs standalone)")
                continue
            floor_match = FLOOR_RE.match(rest)
            if not floor_match:
                errors.append(f"{where}: unrecognized requirement format, expected '>=X.Y[,<Z]'")
                continue
            base, upper = floor_match.groups()

            if driver == "pycubrid" and directory in EXACT_PYCUBRID_FLOOR:
                expected = EXACT_PYCUBRID_FLOOR[directory]
                actual = base + (upper or "")
                if actual != expected:
                    errors.append(f"{where}: expected pycubrid>={expected} in {directory}")
                continue
            if driver == "pycubrid" and directory in template_pycubrid_dirs:
                actual = base + (upper or "")
                if actual != TEMPLATE_PYCUBRID_FLOOR:
                    errors.append(
                        f"{where}: expected pycubrid>={TEMPLATE_PYCUBRID_FLOOR} (template floor) in {directory}"
                    )
                continue
            if driver == "sqlalchemy-cubrid" and directory in template_sqlalchemy_dirs:
                actual = base + (upper or "")
                if actual != TEMPLATE_SQLALCHEMY_FLOOR:
                    errors.append(
                        f"{where}: expected sqlalchemy-cubrid>={TEMPLATE_SQLALCHEMY_FLOOR} "
                        f"(template floor) in {directory}"
                    )
                continue
            if driver == "sqlalchemy-cubrid" and directory in ADVANCED_SQLALCHEMY_DIRS:
                if base != ADVANCED_SQLALCHEMY_FLOOR or upper:
                    errors.append(
                        f"{where}: expected sqlalchemy-cubrid>={ADVANCED_SQLALCHEMY_FLOOR}, no upper bound "
                        f"(advanced SQLAlchemy floor) in {directory}"
                    )
                continue

            # Everything else must sit exactly on the documented global floor,
            # with no upper bound (the SUPPORT_MATRIX.md table floor is
            # one-sided): higher (undocumented), lower (stale), or an
            # unexpected upper bound is drift either way.
            if base != global_floors[driver] or upper:
                errors.append(
                    f"{where}: expected {driver}>={global_floors[driver]}, no upper bound "
                    f"(global floor) in {directory}, or add {directory!r} as a documented "
                    f"exception in {Path(__file__).name} and SUPPORT_MATRIX.md"
                )

    for label, dirs in (
        ("fundamentals/pycubrid exception", EXACT_PYCUBRID_FLOOR),
        ("advanced SQLAlchemy floor", {d: None for d in ADVANCED_SQLALCHEMY_DIRS}),
    ):
        for directory in dirs:
            if not (root / directory).is_dir():
                errors.append(f"{label}: {directory!r} no longer exists (stale exception)")

    return errors


def main() -> int:
    errors = check(REPO_ROOT, MATRIX_PATH.read_text(encoding="utf-8"))
    if errors:
        print("Dependency floors are out of date with SUPPORT_MATRIX.md (#152):")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("Recipe dependency floors match the documented support contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
