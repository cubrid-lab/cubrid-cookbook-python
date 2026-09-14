from __future__ import annotations
import glob
import os
import runpy
from urllib.parse import urlparse

import pytest

CUBRID_TEST_URL = os.getenv("CUBRID_TEST_URL")
pytestmark = pytest.mark.skipif(
    not CUBRID_TEST_URL,
    reason="CUBRID_live instance URL (CUBRID_TEST_URL) not provided. Skipping live DB tests.",
)


@pytest.fixture(autouse=True)
def setup_database_url():
    """
    Ensure ai-agent recipes connect to the live CUBRID test instance.

    Unlike the dashboard recipes, the ai-agent recipes don't all read a
    single DATABASE_URL - 01/03/04 call pycubrid.connect() directly with
    discrete CUBRID_HOST/CUBRID_PORT/CUBRID_USER/CUBRID_PASSWORD/
    CUBRID_DATABASE env vars (the same names 02_mcp_toolchain.py already
    used), and 05 uses a SQLAlchemy DATABASE_URL like the dashboard
    recipes do. CUBRID_TEST_URL is parsed once here and fans out into
    both shapes so a single env var still drives every recipe.
    """
    if not CUBRID_TEST_URL:
        return

    parsed = urlparse(CUBRID_TEST_URL)
    os.environ["CUBRID_URL"] = CUBRID_TEST_URL
    os.environ["DATABASE_URL"] = CUBRID_TEST_URL
    os.environ["CUBRID_HOST"] = parsed.hostname or "localhost"
    os.environ["CUBRID_PORT"] = str(parsed.port or 33000)
    os.environ["CUBRID_USER"] = parsed.username or "dba"
    os.environ["CUBRID_PASSWORD"] = parsed.password or ""
    os.environ["CUBRID_DATABASE"] = parsed.path.lstrip("/") or "testdb"


AI_AGENT_RECIPES = glob.glob("templates/ai-agent/*.py")


@pytest.mark.parametrize("app_path", AI_AGENT_RECIPES)
def test_ai_agent_recipes_runs_without_errors(app_path):
    """
    Test that each ai-agent recipe runs to completion without raising any
    exception against a live CUBRID database instance.

    Recipes are plain scripts (not Streamlit apps like the dashboard
    recipes), so `runpy.run_path` executes each one exactly as running it
    directly would (`if __name__ == "__main__": main()` included) - an
    uncaught exception fails the test with its real traceback.
    """
    runpy.run_path(app_path, run_name="__main__")
