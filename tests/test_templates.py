from __future__ import annotations
import glob
import os
import pytest
from streamlit.testing.v1 import AppTest

CUBRID_TEST_URL = os.getenv("CUBRID_TEST_URL")
pytestmark = pytest.mark.skipif(
    not CUBRID_TEST_URL,
    reason="CUBRID live instance URL (CUBRID_TEST_URL) not provided. Skipping live DB tests.",
)


@pytest.fixture(autouse=True)
def setup_database_url():
    """Ensure templates connect to the live CUBRID test instance."""
    if CUBRID_TEST_URL:
        os.environ["CUBRID_URL"] = CUBRID_TEST_URL
        os.environ["DATABASE_URL"] = CUBRID_TEST_URL


# Combined both template directories
TEMPLATE_RECIPES = glob.glob("templates/dashboard/*.py") + glob.glob("templates/ai-agent/*.py")


@pytest.mark.parametrize("app_path", TEMPLATE_RECIPES)
def test_template_recipes_runs_without_errors(app_path):
    """
    Test that each Streamlit recipe runs without throwing any UI exceptions against a live CUBRID database instance.
    Note: This is a first-render smoke test.
    """
    at = AppTest.from_file(app_path)
    at.run()

    assert not at.exception, (
        f"App '{app_path}' crashed with exception: {at.exception[0] if at.exception else 'Unknown Error'}"
    )
