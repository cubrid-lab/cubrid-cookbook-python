"""Offline guard: each quickstart app connects to the database its Compose file creates.

The quickstarts are the first thing a reader runs, and CI never starts their own
Compose files. ``5min-sqlalchemy`` once created ``demodb`` while its app connected
to ``testdb`` (#324), so following the README failed at connect. The files are read
as text, so no YAML parser or database is needed.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

QUICKSTART = Path(__file__).resolve().parents[1] / "quickstart"
# ``CUBRID_DB: <name>`` in the service environment.
COMPOSE_DB = re.compile(r"^\s*CUBRID_DB:\s*['\"]?(\w+)['\"]?\s*$", re.MULTILINE)
# The database the health check queries: ``csql ... "dba", "<name>", "-c"``.
HEALTHCHECK_DB = re.compile(r'"csql",\s*"-u",\s*"dba",\s*"(\w+)"')
# ``cubrid+pycubrid://...:33000/<name>`` URLs and ``database="<name>"`` arguments.
APP_DB = re.compile(r"""cubrid\+pycubrid://[^/"']*/(\w+)|database\s*=\s*["'](\w+)["']""")


def app_databases(text: str) -> set[str]:
    """Return every database name an app connects to.

    >>> sorted(app_databases('URL = "cubrid+pycubrid://dba@localhost:33000/testdb"'))
    ['testdb']
    >>> sorted(app_databases('connect(database="demodb", user="dba")'))
    ['demodb']
    """
    return {url or arg for url, arg in APP_DB.findall(text)}


class QuickstartDatabaseTests(unittest.TestCase):
    def quickstarts(self) -> list[Path]:
        found = sorted(p.parent for p in QUICKSTART.glob("*/docker-compose.yml"))
        self.assertGreaterEqual(len(found), 2)
        return found

    def test_app_connects_to_the_compose_database(self) -> None:
        for directory in self.quickstarts():
            with self.subTest(quickstart=directory.name):
                compose = (directory / "docker-compose.yml").read_text(encoding="utf-8")
                created = COMPOSE_DB.findall(compose)
                self.assertEqual(len(created), 1, "expected one CUBRID_DB entry")
                self.assertEqual(HEALTHCHECK_DB.findall(compose), created)
                used = app_databases((directory / "app.py").read_text(encoding="utf-8"))
                self.assertEqual(used, set(created))

    def test_parsers_see_the_324_mismatch(self) -> None:
        # The pre-#324 pair: Compose created demodb, the app used testdb.
        url = 'DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"'
        self.assertEqual(app_databases(url), {"testdb"})
        compose = '    environment:\n      CUBRID_DB: demodb\n    test: ["CMD", "csql", "-u", "dba", "demodb", "-c"]'
        self.assertEqual(COMPOSE_DB.findall(compose), ["demodb"])
        self.assertEqual(HEALTHCHECK_DB.findall(compose), ["demodb"])
        self.assertEqual(app_databases('connect(database="demodb", user="dba")'), {"demodb"})


if __name__ == "__main__":
    unittest.main()
