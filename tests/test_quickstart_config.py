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

ROOT = Path(__file__).resolve().parents[1]
QUICKSTART = ROOT / "quickstart"
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

    def test_compose_keeps_the_lab_local_and_its_data_named(self) -> None:
        # #386: the READMEs promise a local-only lab whose data survives `down`.
        for directory in self.quickstarts():
            with self.subTest(quickstart=directory.name):
                compose = (directory / "docker-compose.yml").read_text(encoding="utf-8")
                ports = re.findall(r'^\s*- "([^"]+:\d+)"', compose, re.MULTILINE)
                self.assertTrue(ports)
                for port in ports:
                    self.assertTrue(port.startswith("127.0.0.1:"), port)
                self.assertRegex(compose, r"\n    hostname: cubrid-[\w-]+\n")
                for volume in ("cubrid_data", "cubrid_databases"):
                    self.assertRegex(compose, rf"\n\s+- {volume}:/")
                    self.assertRegex(compose, rf"\nvolumes:\n(?:  \w+:\n)*  {volume}:\n")

    def test_fastapi_api_has_a_healthcheck_for_compose_wait(self) -> None:
        # `docker compose up --wait` returns before Uvicorn listens without one.
        compose = (QUICKSTART / "5min-fastapi/docker-compose.yml").read_text(encoding="utf-8")
        api = compose.split("\n  api:\n", 1)[1].split("\nvolumes:\n", 1)[0]
        self.assertIn("healthcheck:", api)
        self.assertIn("http://127.0.0.1:8000/", api)

    def test_sqlalchemy_readmes_show_the_golden_output(self) -> None:
        directory = QUICKSTART / "5min-sqlalchemy"
        golden = (directory / "expected/app.expected").read_text(encoding="utf-8")
        block = f"```text\n{golden.rstrip()}\n```"
        for page in (directory / "README.md", ROOT / "docs/ko/quickstart-sqlalchemy.md"):
            with self.subTest(page=page.name):
                self.assertIn(block, page.read_text(encoding="utf-8"))

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
