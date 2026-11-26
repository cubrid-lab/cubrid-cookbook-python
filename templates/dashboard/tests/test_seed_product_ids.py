"""Sales seeding must use the product IDs the database actually assigned (#622)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent


def _seed_table_viewer(module) -> None:
    with module.get_engine().begin() as connection:
        module.create_tables(connection)
        module.seed_if_empty(connection)


SEEDERS = {
    "01_table_viewer.py": _seed_table_viewer,
    "02_filters.py": lambda module: module.setup_schema(seed_only=True),
    "03_kpis.py": lambda module: module.ensure_data(),
    "05_form_crud.py": lambda module: module.bootstrap(),
}


def _load(name: str, monkeypatch: pytest.MonkeyPatch):
    spec = importlib.util.spec_from_file_location(
        f"dashboard_seed_{name.removesuffix('.py')}", DASHBOARD_ROOT / name
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("recipe", sorted(SEEDERS))
def test_sales_reference_existing_products_when_ids_do_not_start_at_one(
    recipe: str, dashboard_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load(recipe, monkeypatch)
    engine = create_engine(dashboard_database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS cookbook_dashboard_sales"))
            connection.execute(text("DROP TABLE IF EXISTS cookbook_dashboard_products"))

        SEEDERS[recipe](module)

        # Leave products with IDs 6..10 and no sales, as after earlier inserts and deletes.
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM cookbook_dashboard_sales"))
            connection.execute(
                text("DELETE FROM cookbook_dashboard_products WHERE product_id <= 5")
            )

        SEEDERS[recipe](module)

        with engine.connect() as connection:
            product_ids = {
                int(row[0])
                for row in connection.execute(
                    text("SELECT product_id FROM cookbook_dashboard_products")
                )
            }
            sold_ids = [
                int(row[0])
                for row in connection.execute(
                    text("SELECT product_id FROM cookbook_dashboard_sales")
                )
            ]
        assert product_ids == {6, 7, 8, 9, 10}
        assert sold_ids, "sample sales were not seeded"
        assert set(sold_ids) <= product_ids

        # Seeding again must not duplicate the sample sales.
        SEEDERS[recipe](module)
        with engine.connect() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM cookbook_dashboard_sales")
            ).scalar_one()
        assert count == len(sold_ids)
    finally:
        engine.dispose()
