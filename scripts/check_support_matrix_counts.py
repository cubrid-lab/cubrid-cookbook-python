#!/usr/bin/env python3
"""check_support_matrix_counts.py - Keep SUPPORT_MATRIX recipe counts honest.

The "Recipe Coverage" table in SUPPORT_MATRIX.md is the only place recipe
counts are written down. Each table row maps to exactly one counting rule
below, and the script fails when a row's number differs from the repository:

* Golden-backed rows count ``expected/*.expected`` files under their
  directories, the same files ``make verify`` runs. Every golden must belong
  to exactly one row, so a new golden directory forces a table update.
* Flask and FastAPI rows count recipe directories that have a ``tests/``
  directory, the same ``*/tests`` discovery the smoke-test workflow uses.
* Script rows count numbered ``NN_*.py`` scripts in the template directory.
* Single-application templates (Django, Celery, FastAPI quickstart) are one
  recipe each; their row fails if the application directory disappears.

The **Total** row must equal the sum of the rows, and its "N golden-backed"
note, when present, must equal the number of goldens. Prose elsewhere should
point at the table instead of repeating these numbers.

The "Driver & Framework Versions" table must also state the SQLAlchemy range the
dialect supports (``SQLALCHEMY_SUPPORTED``) and its reviewed status wording, and the
one-line dialect descriptions listed in ``SQLALCHEMY_CLAIMS`` must use the reviewed
wording verbatim; any other range, such as one that promotes 2.2, fails the check.

Usage:
    python scripts/check_support_matrix_counts.py

Exit code 0 when the table matches the repository; 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = REPO_ROOT / "SUPPORT_MATRIX.md"
TABLE_HEADER = "| Category | Recipes | Verified by |"

# Reviewed SQLAlchemy range of the dialect, kept here with its pinned upstream reference:
# sqlalchemy-cubrid docs/SUPPORT_MATRIX.md at da9c3977d21e94f739667ae5e9467c04d53fdd0b
# lists 2.0.x and 2.1.x as supported and >= 2.2 as not supported. Change it only after
# the dialect documents a new range; this check does not read the network.
SQLALCHEMY_SUPPORTED = "2.0, 2.1"
SQLALCHEMY_STATUS = (
    "✅ Supported range of the dialect; 2.2 is not supported (see below). Async recipes install"
    " the `sqlalchemy[asyncio]` extra for the required greenlet runtime"
)
# File -> exact wording its current dialect description must contain.
SQLALCHEMY_CLAIMS: dict[str, str] = {
    "README.md": "SQLAlchemy 2.0/2.1 dialect for CUBRID",
    "docs/README.ko.md": "CUBRID용 SQLAlchemy 2.0/2.1 방언",
    "docs/index.md": "SQLAlchemy 2.0/2.1 dialect",
    "llms.txt": "SQLAlchemy 2.0/2.1 dialect for CUBRID",
    ".github/ISSUE_TEMPLATE/config.yml": "SQLAlchemy 2.0/2.1 dialect for CUBRID",
}

# Table label -> directories whose expected/*.expected goldens the row counts.
GOLDEN_ROWS: dict[str, tuple[str, ...]] = {
    "pycubrid fundamentals": ("fundamentals/pycubrid",),
    "SQLAlchemy fundamentals": ("fundamentals/sqlalchemy",),
    "SQLAlchemy ORM basics": ("fundamentals/orm-basics",),
    "Pandas fundamentals": ("fundamentals/pandas",),
    "Error-handling topic": ("fundamentals/error-handling",),
    "Async + Alembic + JSON + Isolation": (
        "fundamentals/async",
        "fundamentals/alembic",
        "fundamentals/json",
        "fundamentals/isolation-levels",
    ),
    "Java-to-Python migration": ("migration/java-to-python",),
    "SQLAlchemy quickstart": ("quickstart/5min-sqlalchemy",),
    "Pandas batch-etl template": ("templates/batch-etl",),
    "Pitfalls: reserved-word DDL": ("pitfalls/reserved-words",),
}


def golden_paths(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("expected/*.expected") if p.is_file())


def count_goldens(root: Path, dirs: tuple[str, ...]) -> int:
    return sum(len(golden_paths(root / d)) for d in dirs if (root / d).is_dir())


def count_suites(root: Path, recipes_dir: str) -> int:
    """Count recipe directories with a tests/ directory (smoke-test discovery)."""
    base = root / recipes_dir
    if not base.is_dir():
        return 0
    return sum(1 for d in base.iterdir() if (d / "tests").is_dir())


def count_scripts(root: Path, template_dir: str) -> int:
    base = root / template_dir
    return sum(1 for p in base.glob("[0-9][0-9]_*.py") if p.is_file()) if base.is_dir() else 0


def count_app(root: Path, marker: str) -> int:
    """A single-application template is one recipe while its entry point exists."""
    return 1 if (root / marker).is_file() else 0


OTHER_ROWS: dict[str, Callable[[Path], int]] = {
    "Flask templates": lambda r: count_suites(r, "templates/flask"),
    "FastAPI templates": lambda r: count_suites(r, "templates/api-service-fastapi/recipes"),
    "FastAPI quickstart": lambda r: count_app(r, "quickstart/5min-fastapi/app.py"),
    "AI agent template": lambda r: count_scripts(r, "templates/ai-agent"),
    "Streamlit templates": lambda r: count_scripts(r, "templates/dashboard"),
    "Django template": lambda r: count_app(r, "templates/django/manage.py"),
    "Celery async-worker template": lambda r: count_app(r, "templates/async-worker/app.py"),
}


def parse_table(matrix: str) -> list[list[str]]:
    """Return the Recipe Coverage table's body rows as lists of stripped cells."""
    lines = matrix.splitlines()
    try:
        start = lines.index(TABLE_HEADER)
    except ValueError:
        return []
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def check(root: Path, matrix: str) -> list[str]:
    rows = parse_table(matrix)
    if not rows:
        return [f"Recipe Coverage table header not found: {TABLE_HEADER!r}"]

    errors: list[str] = []
    seen: set[str] = set()
    total_cells: list[str] | None = None
    row_sum = 0
    golden_sum = 0
    for cells in rows:
        label = cells[0]
        if len(cells) != 3:
            errors.append(f"row {label!r}: expected 3 cells, found {len(cells)}")
            continue
        if label in seen or (label == "**Total**" and total_cells is not None):
            errors.append(f"row {label!r} appears more than once")
            continue
        if label == "**Total**":
            total_cells = cells
            continue
        try:
            claimed = int(cells[1])
        except ValueError:
            errors.append(f"row {label!r}: recipe count {cells[1]!r} is not a number")
            continue
        if label in GOLDEN_ROWS:
            actual = count_goldens(root, GOLDEN_ROWS[label])
            golden_sum += actual
        elif label in OTHER_ROWS:
            actual = OTHER_ROWS[label](root)
        else:
            errors.append(f"row {label!r}: no counting rule; add one to {Path(__file__).name}")
            continue
        seen.add(label)
        row_sum += actual
        if claimed != actual:
            errors.append(f"row {label!r}: table says {claimed}, repository has {actual}")

    for label in sorted((GOLDEN_ROWS.keys() | OTHER_ROWS.keys()) - seen):
        errors.append(f"row {label!r} is missing from the table")

    goldens = golden_paths(root)
    if golden_sum != len(goldens):
        covered = {
            p
            for dirs in GOLDEN_ROWS.values()
            for d in dirs
            if (root / d).is_dir()
            for p in golden_paths(root / d)
        }
        uncovered = [p for p in goldens if p not in covered]
        for p in uncovered:
            errors.append(f"golden {p.relative_to(root)} is not counted by any table row")
        if not uncovered:
            errors.append(
                f"golden-backed rows count {golden_sum} goldens, repository has {len(goldens)}"
                " (overlapping directories in GOLDEN_ROWS?)"
            )

    if total_cells is None:
        errors.append("**Total** row is missing")
    else:
        claimed_total = total_cells[1].strip("*") if len(total_cells) > 1 else ""
        if claimed_total != str(row_sum):
            errors.append(f"**Total** row says {claimed_total}, rows sum to {row_sum}")
        note = re.search(r"(\d+) golden-backed", total_cells[2] if len(total_cells) > 2 else "")
        if note and int(note.group(1)) != len(goldens):
            errors.append(
                f"**Total** row says {note.group(1)} golden-backed, repository has {len(goldens)}"
            )
    return errors


def check_sqlalchemy_range(root: Path, matrix: str) -> list[str]:
    """Require the reviewed SQLAlchemy range, verbatim, in every current support claim."""
    errors: list[str] = []
    rows = [
        [c.strip() for c in line.strip().strip("|").split("|")]
        for line in matrix.splitlines()
        if line.startswith("| SQLAlchemy |")
    ]
    if len(rows) != 1 or len(rows[0]) != 3:
        errors.append("expected one 3-cell 'SQLAlchemy' row in Driver & Framework Versions")
    else:
        if rows[0][1] != SQLALCHEMY_SUPPORTED:
            errors.append(
                f"SQLAlchemy row says {rows[0][1]!r}, the reviewed supported range is"
                f" {SQLALCHEMY_SUPPORTED!r}"
            )
        if rows[0][2] != SQLALCHEMY_STATUS:
            errors.append("SQLAlchemy row status differs from the reviewed wording")
    for name, wording in SQLALCHEMY_CLAIMS.items():
        path = root / name
        if not path.is_file() or wording not in path.read_text(encoding="utf-8"):
            errors.append(f"{name} must say {wording!r} (reviewed range {SQLALCHEMY_SUPPORTED})")
    return errors


def main() -> int:
    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    failed = False
    for header, errors in (
        ("SUPPORT_MATRIX.md Recipe Coverage table is out of date:", check(REPO_ROOT, matrix)),
        (
            "SQLAlchemy support claims differ from the reviewed range:",
            check_sqlalchemy_range(REPO_ROOT, matrix),
        ),
    ):
        if errors:
            failed = True
            print(header)
            for err in errors:
                print(f"  - {err}")
    if failed:
        return 1
    print("SUPPORT_MATRIX.md Recipe Coverage counts and SQLAlchemy range match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
