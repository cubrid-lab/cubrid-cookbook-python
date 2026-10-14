"""Offline check: the SQLAlchemy quickstart cleans up even when a drop fails (#332).

``quickstart/5min-sqlalchemy/app.py`` drops its Core and ORM tables each in its
own ``try`` inside a ``finally`` block and always disposes of the engine. The
golden only covers a successful run, so this test runs ``main()`` against a
throwaway SQLite file and makes one cleanup drop raise. The ORM drop
and ``engine.dispose()`` must still run. Only ``sqlalchemy`` is needed.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

APP = Path(__file__).resolve().parents[1] / "quickstart" / "5min-sqlalchemy" / "app.py"


def load_app() -> ModuleType:
    """Import a fresh copy of the quickstart app (its own ORM ``Base``)."""
    name = "quickstart_sqlalchemy_app"
    spec = importlib.util.spec_from_file_location(name, APP)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # SQLAlchemy resolves the ``Mapped[...]`` annotations through sys.modules.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[name]
    return module


class QuickstartCleanupTests(unittest.TestCase):
    def run_main(
        self, app: ModuleType, fail_on: str
    ) -> tuple[int, str, mock.Mock, list[str], Engine]:
        """Run ``main()`` on SQLite; the cleanup drop of ``fail_on`` raises."""
        # A file, not :memory:, so the tables outlive the engine's dispose().
        workdir = tempfile.TemporaryDirectory()
        self.addCleanup(workdir.cleanup)
        engine = create_engine(f"sqlite:///{Path(workdir.name) / 'quickstart.db'}")
        self.addCleanup(engine.dispose)
        dispose = mock.Mock(wraps=engine.dispose)
        engine.dispose = dispose  # type: ignore[method-assign]
        calls: list[str] = []
        tables = {"core": app.metadata, "orm": app.Base.metadata}
        originals = {name: meta.drop_all for name, meta in tables.items()}

        def recording_drop(name: str):
            def drop_all(bind, *args, **kwargs):
                calls.append(name)
                # The first drop of each set runs at setup; the second is cleanup.
                if name == fail_on and calls.count(name) == 2:
                    raise OperationalError("DROP TABLE", {}, Exception("simulated lock"))
                return originals[name](bind, *args, **kwargs)

            return drop_all

        out = io.StringIO()
        with (
            mock.patch.object(app, "create_engine", return_value=engine),
            mock.patch.object(app.metadata, "drop_all", recording_drop("core")),
            mock.patch.object(app.Base.metadata, "drop_all", recording_drop("orm")),
            contextlib.redirect_stdout(out),
        ):
            status = app.main()
        return status, out.getvalue(), dispose, calls, engine

    def test_failed_core_drop_still_drops_orm_tables_and_disposes(self) -> None:
        app = load_app()
        status, output, dispose, calls, engine = self.run_main(app, fail_on="core")

        self.assertEqual(status, 0)
        self.assertIn("Cleanup failed:", output)
        # Setup drops both sets, cleanup tries both: the ORM drop still ran.
        self.assertEqual(calls, ["core", "orm", "core", "orm"])
        dispose.assert_called_once()
        # Only the table whose drop failed is left behind.
        remaining = set(inspect(engine).get_table_names())
        self.assertEqual(remaining, {"cookbook_core_items"})

    def test_failed_orm_drop_still_disposes(self) -> None:
        app = load_app()
        status, output, dispose, calls, engine = self.run_main(app, fail_on="orm")

        self.assertEqual(status, 0)
        self.assertIn("Cleanup failed:", output)
        self.assertEqual(calls, ["core", "orm", "core", "orm"])
        dispose.assert_called_once()
        self.assertEqual(set(inspect(engine).get_table_names()), {"cookbook_orm_items"})


if __name__ == "__main__":
    unittest.main()
