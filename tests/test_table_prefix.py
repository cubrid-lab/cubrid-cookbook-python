"""Offline guard: every table a template declares carries the ``cookbook_`` prefix.

Recipes are often pointed at a reader's real database, so unprefixed names such as
``users`` or ``orders`` could collide with existing tables. The models are parsed
with ``ast`` (nothing is imported), so no Flask/FastAPI install is needed.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
PREFIX = "cookbook_"
# Names shared by more than one recipe before the prefix change; their suites must
# run one at a time. Tracked in #277. This set should shrink to empty, at which
# point the guard becomes a strict no-sharing check. Do not add to it: give a new
# recipe's table a distinct name instead.
KNOWN_SHARED = {
    "cookbook_categories",
    "cookbook_products",
}


def declared_tables(path: Path) -> list[tuple[int, str]]:
    """Return (line, name) for each ``__tablename__`` and ``Table("name", ...)``."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        value = None
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in node.targets):
                value = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "__tablename__":
                value = node.value
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name == "Table" and node.args:
                value = node.args[0]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            found.append((node.lineno, value.value))
    return found


class TableNamePrefixTests(unittest.TestCase):
    def test_models_found(self) -> None:
        self.assertGreater(len(list(TEMPLATES.glob("**/models.py"))), 20)

    def test_every_template_table_has_cookbook_prefix(self) -> None:
        offenders = []
        total = 0
        for path in sorted(TEMPLATES.glob("**/models.py")):
            for line, name in declared_tables(path):
                total += 1
                if not name.startswith(PREFIX):
                    offenders.append(f"{path.relative_to(TEMPLATES.parent)}:{line}: {name}")
        self.assertGreater(total, 40)
        self.assertEqual(offenders, [], "tables must start with 'cookbook_'")

    def test_no_table_name_is_shared_between_recipes(self) -> None:
        owners: dict[str, set[str]] = {}
        for path in sorted(TEMPLATES.glob("**/models.py")):
            recipe = str(path.parent.relative_to(TEMPLATES.parent))
            for _, name in declared_tables(path):
                owners.setdefault(name, set()).add(recipe)
        shared = {
            name: sorted(dirs)
            for name, dirs in owners.items()
            if len(dirs) > 1 and name not in KNOWN_SHARED
        }
        self.assertEqual(shared, {}, "recipes sharing a table cannot run on one database")


if __name__ == "__main__":
    unittest.main()
