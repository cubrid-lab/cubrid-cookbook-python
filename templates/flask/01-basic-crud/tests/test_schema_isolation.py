"""Regression test for #142.

A leftover ``templates/dashboard`` ``cookbook_sales`` table (foreign-keyed to
this recipe's ``cookbook_products``) must not block this recipe's teardown.
This reproduces the reported CUBRID failure — errno=-923, "primary key ...
referred by a foreign key ... is not supposed to be dropped" — entirely
offline: SQLAlchemy's SQLite driver leaves foreign-key enforcement off by
default, unlike CUBRID which always enforces it, so this test turns it on
for one throwaway engine to get the same failure mode SQLite is otherwise
too permissive to reproduce.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import NullPool

RECIPE_ROOT = Path(__file__).resolve().parents[1]
if str(RECIPE_ROOT) not in sys.path:
    sys.path.insert(0, str(RECIPE_ROOT))

from conftest import _drop_cross_recipe_leftovers  # noqa: E402


def test_leftover_dashboard_sales_table_does_not_block_products_drop(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'leftover.db'}"
    engine = create_engine(url, poolclass=NullPool)

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    try:
        # Simulate the dashboard suite leaving its tables behind: the same
        # cookbook_products/cookbook_sales shape templates/dashboard's
        # recipes create (see templates/dashboard/*.py), with foreign-key
        # enforcement on so SQLite reproduces CUBRID's errno=-923.
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE cookbook_products (product_id INTEGER PRIMARY KEY)")
            )
            connection.execute(
                text(
                    "CREATE TABLE cookbook_sales ("
                    "sale_id INTEGER PRIMARY KEY, "
                    "product_id INTEGER NOT NULL, "
                    "FOREIGN KEY (product_id) REFERENCES cookbook_products(product_id))"
                )
            )
            connection.execute(text("INSERT INTO cookbook_products VALUES (1)"))
            connection.execute(text("INSERT INTO cookbook_sales VALUES (1, 1)"))

        # Without the defensive drop, the next statement raises
        # sqlite3.IntegrityError here (CUBRID: errno=-923) because
        # cookbook_sales still references cookbook_products.
        _drop_cross_recipe_leftovers(engine)

        with engine.begin() as connection:
            connection.execute(text("DROP TABLE cookbook_products"))
            tables = (
                connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                .scalars()
                .all()
            )
        assert "cookbook_sales" not in tables
        assert "cookbook_products" not in tables
    finally:
        engine.dispose()
