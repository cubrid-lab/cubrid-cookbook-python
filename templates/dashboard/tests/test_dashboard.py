"""AppTest suite for the templates/dashboard Streamlit recipes.

Exercises every recipe with Streamlit's ``st.testing.v1.AppTest`` (no browser
or real server), plus the specific assertions from issue #103: the seeded
table viewer renders rows, the KPI page's metrics are non-empty, and the
sidebar filters change the rendered dataframe's shape. See ``conftest.py``
for how ``CUBRID_TEST_URL`` selects a live CUBRID database or an offline
SQLite fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
# Absolute paths: AppTest.from_file resolves a relative path against the
# *test file's* directory, not the current working directory, so a bare
# glob.glob("templates/dashboard/*.py") (relative to the CWD) silently
# resolves to the wrong place when pytest is not started from templates/dashboard.
RECIPE_PATHS = sorted(DASHBOARD_ROOT.glob("[0-9][0-9]_*.py"))
RECIPE_IDS = [path.name for path in RECIPE_PATHS]

# AppTest.run()'s default 3-second script-run timeout is tight for a recipe
# that connects to a live database, creates tables, and seeds rows on every
# run; it flaked under CI load (first connection after another suite had used
# the shared CUBRID broker). 30s matches the live-smoke readiness budget used
# elsewhere in this repo for live CUBRID calls.
RUN_TIMEOUT = 30

TABLE_VIEWER = DASHBOARD_ROOT / "01_table_viewer.py"
FILTERS = DASHBOARD_ROOT / "02_filters.py"
KPIS = DASHBOARD_ROOT / "03_kpis.py"


@pytest.mark.parametrize("recipe_path", RECIPE_PATHS, ids=RECIPE_IDS)
def test_recipe_runs_without_exception(recipe_path: Path) -> None:
    at = AppTest.from_file(str(recipe_path))
    at.run(timeout=RUN_TIMEOUT)

    assert not at.exception, (
        f"{recipe_path.name} crashed with exception: "
        f"{at.exception[0] if at.exception else 'unknown error'}"
    )


def test_table_viewer_renders_seeded_rows() -> None:
    """01_table_viewer.py seeds demo data and renders it on first load."""
    at = AppTest.from_file(str(TABLE_VIEWER))
    at.run(timeout=RUN_TIMEOUT)

    assert not at.exception
    assert len(at.dataframe) == 1
    rows = at.dataframe[0].value
    assert len(rows) > 0
    assert {"product_name", "category_name", "quantity"}.issubset(rows.columns)


def test_kpi_metrics_are_non_empty() -> None:
    """03_kpis.py's four metric cards all render a populated value."""
    at = AppTest.from_file(str(KPIS))
    at.run(timeout=RUN_TIMEOUT)

    assert not at.exception
    metrics = at.metric
    assert len(metrics) == 4
    for metric in metrics:
        assert metric.value not in (None, "")


def test_filters_change_dataframe_shape() -> None:
    """02_filters.py's category filter narrows the rendered dataframe.

    The default view is not unfiltered: the sidebar price slider already
    defaults to a 0-500 USD range, so this only narrows further by category.
    """
    at = AppTest.from_file(str(FILTERS))
    at.run(timeout=RUN_TIMEOUT)
    assert not at.exception

    default_view_rows = len(at.dataframe[0].value)
    assert default_view_rows > 0

    category_select = at.sidebar.selectbox[0]
    narrower_category = next(c for c in category_select.options if c != "All")
    at.sidebar.selectbox[0].set_value(narrower_category).run(timeout=RUN_TIMEOUT)

    assert not at.exception
    filtered_rows = len(at.dataframe[0].value)
    assert filtered_rows != default_view_rows
    assert filtered_rows < default_view_rows
