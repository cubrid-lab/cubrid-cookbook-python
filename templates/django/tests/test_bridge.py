"""Live CUBRID round trip through the documented Django/SQLAlchemy bridge."""

from __future__ import annotations

import json
from types import ModuleType


def test_http_items_and_sqlalchemy_update_delete(
    django_bridge: tuple[ModuleType, ModuleType],
) -> None:
    from django.test import Client

    db, _views = django_bridge
    client = Client()

    # The first request exercises the view's lazy SQLAlchemy schema creation.
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "db": 1}

    created = client.post(
        "/items",
        data=json.dumps({"title": "cb128-first", "is_active": False}),
        content_type="application/json",
    )
    assert created.status_code == 201
    item_id = created.json()["id"]
    assert created.json() == {"id": item_id, "title": "cb128-first", "is_active": 0}

    with db.get_session() as session:
        persisted = session.get(db.CookbookItem, item_id)
        assert persisted is not None
        assert persisted.title == "cb128-first"
        assert persisted.is_active == 0
        persisted.title = "cb128-updated"
        session.commit()

    listed = client.get("/items")
    assert listed.status_code == 200
    assert listed.json() == {"items": [{"id": item_id, "title": "cb128-updated", "is_active": 0}]}

    with db.get_session() as session:
        persisted = session.get(db.CookbookItem, item_id)
        assert persisted is not None
        session.delete(persisted)
        session.commit()

    assert client.get("/items").json() == {"items": []}
