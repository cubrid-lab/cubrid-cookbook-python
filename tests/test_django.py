from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select
from templates.django.app.db import CookbookItem, create_tables, get_session

CUBRID_TEST_URL = os.getenv("CUBRID_TEST_URL")

pytestmark = pytest.mark.skipif(
    not CUBRID_TEST_URL,
    reason="CUBRID live instance URL (CUBRID_TEST_URL) not provided. Skipping live DB tests.",
)


def test_django_cubrid_round_trip():
    create_tables()

    session = get_session()
    title = f"pytest-cubrid-smoke-test-{uuid.uuid4().hex}"

    try:
        item = CookbookItem(
            title=title,
            is_active=1,
        )

        session.add(item)
        session.commit()

        saved = session.execute(
            select(CookbookItem).where(
                CookbookItem.title == title
            )
        ).scalar_one()

        assert saved.title == title
        assert saved.is_active == 1

        saved.is_active = 0
        session.commit()

        updated = session.execute(
            select(CookbookItem).where(
                CookbookItem.id == saved.id
            )
        ).scalar_one()

        assert updated.is_active == 0

    finally:
        session.close()