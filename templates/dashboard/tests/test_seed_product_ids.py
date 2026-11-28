"""Sales seeding must use the real IDs of the intended demo products (#622)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from streamlit.testing.v1 import AppTest

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


def _reset(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS cookbook_dashboard_sales"))
        connection.execute(text("DROP TABLE IF EXISTS cookbook_dashboard_products"))


def _insert_products(engine, names: list[str]) -> None:
    with engine.begin() as connection:
        for name in names:
            connection.execute(
                text(
                    "INSERT INTO cookbook_dashboard_products "
                    "(product_name, category_name, unit_price_cents, is_active) "
                    "VALUES (:name, 'Other', 100, 1)"
                ),
                {"name": name},
            )


def _ids(engine, table: str, column: str) -> list[int]:
    with engine.connect() as connection:
        return [int(r[0]) for r in connection.execute(text(f"SELECT {column} FROM {table}"))]


def _id_by_name(engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            r[1]: int(r[0])
            for r in connection.execute(
                text("SELECT product_id, product_name FROM cookbook_dashboard_products")
            )
        }


@pytest.fixture
def seeded(request, dashboard_database_url: str, monkeypatch: pytest.MonkeyPatch):
    recipe = request.param
    module = _load(recipe, monkeypatch)
    engine = create_engine(dashboard_database_url)
    _reset(engine)
    SEEDERS[recipe](module)  # creates both tables and seeds them once
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM cookbook_dashboard_sales"))
    yield module, engine, SEEDERS[recipe]
    engine.dispose()


RECIPES = pytest.mark.parametrize("seeded", sorted(SEEDERS), indirect=True)


@RECIPES
def test_sales_use_demo_product_ids_that_do_not_start_at_one(seeded) -> None:
    module, engine, seed = seeded
    # Unrelated products take IDs 1 to 3; the demo products come back as 4 to 13.
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM cookbook_dashboard_products"))
    _insert_products(engine, ["Unrelated A", "Unrelated B", "Unrelated C"])
    _insert_products(engine, list(module.DEMO_PRODUCT_NAMES))
    demo_ids = {
        pid for name, pid in _id_by_name(engine).items() if name in module.DEMO_PRODUCT_NAMES
    }
    assert min(demo_ids) > 3

    seed(module)

    sold = _ids(engine, "cookbook_dashboard_sales", "product_id")
    assert sold, "sample sales were not seeded"
    assert set(sold) <= demo_ids

    # Seeding again must not duplicate the sample sales.
    seed(module)
    assert len(_ids(engine, "cookbook_dashboard_sales", "sale_id")) == len(sold)


@RECIPES
def test_unrelated_products_are_never_used_and_nothing_is_seeded(seeded) -> None:
    module, engine, seed = seeded
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM cookbook_dashboard_products"))
    _insert_products(engine, ["Unrelated A", "Unrelated B"])

    with pytest.raises(RuntimeError, match="demo products"):
        seed(module)

    assert _ids(engine, "cookbook_dashboard_sales", "sale_id") == []
    assert sorted(_id_by_name(engine)) == ["Unrelated A", "Unrelated B"]


@RECIPES
def test_missing_or_edited_demo_product_is_refused(seeded) -> None:
    module, engine, seed = seeded
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE cookbook_dashboard_products SET product_name = 'Desk Lamp (edited)' "
                "WHERE product_name = 'Desk Lamp'"
            )
        )

    with pytest.raises(RuntimeError, match="Desk Lamp"):
        seed(module)

    assert _ids(engine, "cookbook_dashboard_sales", "sale_id") == []


@RECIPES
def test_duplicate_demo_product_name_is_refused(seeded) -> None:
    module, engine, seed = seeded
    _insert_products(engine, ["Desk Lamp"])

    with pytest.raises(RuntimeError, match="Desk Lamp.*2 rows"):
        seed(module)

    assert _ids(engine, "cookbook_dashboard_sales", "sale_id") == []


@RECIPES
def test_fresh_database_seeds_the_same_sales_as_before(seeded) -> None:
    module, engine, seed = seeded
    ids_by_name = _id_by_name(engine)

    seed(module)

    with engine.connect() as connection:
        sold = [
            int(r[0])
            for r in connection.execute(
                text("SELECT product_id FROM cookbook_dashboard_sales ORDER BY sale_id")
            )
        ]
    # The i-th sale is still of the i-th demo product, as with the old (i % 10) + 1.
    assert sold == [ids_by_name[module.DEMO_PRODUCT_NAMES[i % 10]] for i in range(len(sold))]
    assert len(sold) in (12, 15)


@RECIPES
def test_reset_button_stays_reachable_when_a_demo_product_is_missing(seeded) -> None:
    module, engine, _seed = seeded
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE cookbook_dashboard_products SET product_name = 'Desk Lamp (edited)' "
                "WHERE product_name = 'Desk Lamp'"
            )
        )

    at = AppTest.from_file(module.__file__)
    at.run(timeout=30)

    # The page explains the problem and still offers the reset; nothing was reset or seeded.
    assert not at.exception
    assert len(at.error) == 1
    assert "Desk Lamp" in at.error[0].value
    resets = [button for button in at.button if button.label == "Reset Demo Data"]
    assert len(resets) == 1
    assert _ids(engine, "cookbook_dashboard_sales", "sale_id") == []
    assert "Desk Lamp (edited)" in _id_by_name(engine)

    # Clicking it recovers the page: tables are recreated and reseeded.
    resets[0].click()
    at.run(timeout=30)

    assert not at.exception
    assert len(at.error) == 0
    assert _ids(engine, "cookbook_dashboard_sales", "sale_id")
    assert "Desk Lamp" in _id_by_name(engine)
