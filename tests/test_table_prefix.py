"""Offline guard: every example table carries the ``cookbook_`` prefix and one schema.

Recipes are often pointed at a reader's real database, so unprefixed names such as
``users`` or ``orders`` could collide with existing tables. Examples also share one
database in CI and on a reader's machine, so a name that two directories create with
different columns (``cookbook_sales`` once had three schemas, #327) breaks whichever
runs second, or blocks a ``DROP`` through a foreign key.

Every ``*.py`` file under the example roots is parsed with ``ast`` (nothing is
imported, so no Flask/FastAPI install is needed). A table is declared by an ORM
``__tablename__``, a ``Table("name", ...)`` call, a pandas ``to_sql("name", ...)``
call, or raw ``CREATE TABLE`` text in any string, including f-strings whose
``{NAME}`` placeholders refer to module-level string constants. ``tests/``
directories are skipped: their fixtures create throwaway tables on purpose.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates"
EXAMPLE_ROOTS = ("quickstart", "migration", "templates", "performance", "fundamentals", "pitfalls")
PREFIX = "cookbook_"
# Names that more than one directory may declare. Empty: every directory owns
# distinct tables (#277, #327), so the guard is a strict no-sharing check. Do not
# add to it: give a new example's table a distinct name instead.
KNOWN_SHARED: set[str] = set()
# Files that declare one table with several schemas on purpose. Each needs a reason.
MULTI_SCHEMA_FILES = {
    # Creates cookbook_settings with rejected, corrected and quoted column names.
    "pitfalls/reserved-words/01_reserved_words.py",
}

CREATE_TABLE = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)[`\"\]]?\s*\(", re.IGNORECASE
)
# Leading words of a table element that is a constraint, not a column.
CONSTRAINT_WORDS = {"primary", "foreign", "unique", "constraint", "key", "index", "check"}


class Declaration(NamedTuple):
    path: str
    line: int
    name: str
    # Lower-case column names; None when the source does not show them.
    columns: frozenset[str] | None


def _split_top_level(body: str) -> list[str]:
    parts, depth, current = [], 0, []
    for char in body:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def ddl_tables(sql: str) -> list[tuple[str, frozenset[str] | None]]:
    """Return (name, columns) for each ``CREATE TABLE`` in ``sql``.

    >>> [(n, sorted(c)) for n, c in ddl_tables('CREATE TABLE t (id INT, "key" TEXT, KEY (id))')]
    [('t', ['id', 'key'])]
    >>> ddl_tables("CREATE TABLE t (...)")
    [('t', None)]
    """
    found: list[tuple[str, frozenset[str] | None]] = []
    for match in CREATE_TABLE.finditer(sql):
        depth, end = 1, match.end()
        while end < len(sql) and depth:
            depth += {"(": 1, ")": -1}.get(sql[end], 0)
            end += 1
        columns = set()
        for element in _split_top_level(sql[match.end() : end - 1]):
            word = re.match(r"\s*([`\"\[])?(\w+)", element)
            if word and (word.group(1) or word.group(2).lower() not in CONSTRAINT_WORDS):
                columns.add(word.group(2).lower())
        found.append((match.group(1), frozenset(columns) or None))
    return found


def _module_constants(tree: ast.Module) -> dict[str, str]:
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = node.value.value
    return constants


def _text(node: ast.AST | None, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                parts.append(_text(value.value, constants) or "{?}")
            else:
                parts.append(_text(value, constants) or "")
        return "".join(parts)
    return None


def _call_name(node: ast.Call) -> str:
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def _orm_columns(cls: ast.ClassDef) -> frozenset[str] | None:
    columns = set()
    for statement in cls.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            target, value = statement.target.id, statement.value
            if value is None and ast.unparse(statement.annotation).startswith("Mapped["):
                columns.add(target.lower())
                continue
        elif isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            if not isinstance(statement.targets[0], ast.Name):
                continue
            target, value = statement.targets[0].id, statement.value
        else:
            continue
        if isinstance(value, ast.Call) and _call_name(value) in {"Column", "mapped_column"}:
            first = value.args[0] if value.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                columns.add(first.value.lower())
            else:
                columns.add(target.lower())
    return frozenset(columns) or None


def declared_tables(path: Path) -> list[Declaration]:
    """Return every table declaration in the example file ``path``."""
    return source_tables(path.read_text(encoding="utf-8"), path.relative_to(REPO).as_posix())


def source_tables(source: str, rel: str) -> list[Declaration]:
    """Return every table declaration in ``source``, reported as file ``rel``."""
    tree = ast.parse(source)
    constants = _module_constants(tree)
    found: list[Declaration] = []
    # Parts of an f-string are visited separately; only scan the whole string.
    inner = {
        id(value)
        for node in ast.walk(tree)
        if isinstance(node, ast.JoinedStr)
        for value in node.values
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for statement in node.body:
                targets = []
                if isinstance(statement, ast.Assign):
                    targets, value = statement.targets, statement.value
                elif isinstance(statement, ast.AnnAssign):
                    targets, value = [statement.target], statement.value
                if any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in targets):
                    name = _text(value, constants)
                    if name:
                        found.append(Declaration(rel, node.lineno, name, _orm_columns(node)))
        elif isinstance(node, ast.Call) and node.args:
            kind = _call_name(node)
            name = _text(node.args[0], constants) if kind in {"Table", "to_sql"} else None
            if name and kind == "Table":
                columns = {
                    arg.args[0].value.lower()
                    for arg in node.args[1:]
                    if isinstance(arg, ast.Call)
                    and _call_name(arg) == "Column"
                    and arg.args
                    and isinstance(arg.args[0], ast.Constant)
                }
                found.append(Declaration(rel, node.lineno, name, frozenset(columns) or None))
            elif name:
                found.append(Declaration(rel, node.lineno, name, None))
        if isinstance(node, (ast.Constant, ast.JoinedStr)) and id(node) not in inner:
            text = _text(node, constants)
            if text and "CREATE" in text.upper():
                for name, columns in ddl_tables(text):
                    found.append(Declaration(rel, node.lineno, name, columns))
    return found


def example_files() -> list[Path]:
    files = []
    for root in EXAMPLE_ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            if "tests" not in path.relative_to(REPO).parts:
                files.append(path)
    return files


def all_declarations() -> list[Declaration]:
    return [decl for path in example_files() for decl in declared_tables(path)]


class TableNamePrefixTests(unittest.TestCase):
    def test_models_found(self) -> None:
        self.assertGreater(len(list(TEMPLATES.glob("**/models.py"))), 20)

    def test_declarations_found_outside_models(self) -> None:
        paths = {decl.path for decl in all_declarations()}
        self.assertGreater(len(paths), 80)
        # Raw DDL, f-string DDL with a constant and ORM classes outside models.py.
        self.assertIn("fundamentals/pycubrid/02_crud.py", paths)
        self.assertIn("templates/dashboard/01_table_viewer.py", paths)
        self.assertIn("templates/ai-agent/05_chatbot_backend.py", paths)

    def test_every_example_table_has_cookbook_prefix(self) -> None:
        declarations = all_declarations()
        offenders = [
            f"{decl.path}:{decl.line}: {decl.name}"
            for decl in declarations
            if not decl.name.lower().startswith(PREFIX)
        ]
        self.assertGreater(len(declarations), 150)
        self.assertEqual(offenders, [], "tables must start with 'cookbook_'")

    def test_no_table_name_is_shared_between_directories(self) -> None:
        owners: dict[str, set[str]] = {}
        for decl in all_declarations():
            owners.setdefault(decl.name.lower(), set()).add(str(Path(decl.path).parent))
        shared = {
            name: sorted(dirs)
            for name, dirs in owners.items()
            if len(dirs) > 1 and name not in KNOWN_SHARED
        }
        self.assertEqual(shared, {}, "directories sharing a table cannot run on one database")

    def test_each_table_name_has_one_schema(self) -> None:
        schemas: dict[str, dict[frozenset[str], list[str]]] = {}
        for decl in all_declarations():
            if decl.columns is None or decl.path in MULTI_SCHEMA_FILES:
                continue
            by_columns = schemas.setdefault(decl.name.lower(), {})
            by_columns.setdefault(decl.columns, []).append(f"{decl.path}:{decl.line}")
        conflicts = {name: found for name, found in schemas.items() if len(found) > 1}
        self.assertEqual(conflicts, {}, "one table name must mean one set of columns")

    def test_multi_schema_files_still_exist(self) -> None:
        for path in MULTI_SCHEMA_FILES:
            self.assertTrue((REPO / path).is_file(), path)

    def test_parser_sees_each_declaration_form(self) -> None:
        source = (
            'NAME = "cookbook_constant"\n'
            "class A:\n"
            '    __tablename__ = "orm_table"\n'
            "    id: Mapped[int] = mapped_column(primary_key=True)\n"
            "    title: Mapped[str]\n"
            'Table("core_table", metadata, Column("id", Integer))\n'
            'frame.to_sql("pandas_table", engine)\n'
            'cur.execute("CREATE TABLE raw_table (id INT, val INT)")\n'
            'cur.execute(f"CREATE TABLE IF NOT EXISTS {NAME} (id INT)")\n'
        )
        found = {(d.name, d.columns) for d in source_tables(source, "probe.py")}
        self.assertEqual(
            found,
            {
                ("orm_table", frozenset({"id", "title"})),
                ("core_table", frozenset({"id"})),
                ("pandas_table", None),
                ("raw_table", frozenset({"id", "val"})),
                ("cookbook_constant", frozenset({"id"})),
            },
        )


if __name__ == "__main__":
    unittest.main()
