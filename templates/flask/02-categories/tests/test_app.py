# pyright: reportCallIssue=false
from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import sys
from typing import cast

import httpx
from flask import Flask
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import importlib

create_app = importlib.import_module("app").create_app
db = importlib.import_module("database").db
_models = importlib.import_module("models")
Article = _models.Article
Category = _models.Category


@pytest.fixture
def app(tmp_path: Path):
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        }
    )


@pytest.fixture
def httpx_client(app):
    transport = httpx.WSGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://testserver") as c:
        yield c


def _json_object(response: httpx.Response) -> Mapping[str, object]:
    payload = cast(object, json.loads(response.text))
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def _json_int(payload: Mapping[str, object], key: str) -> int:
    value = payload[key]
    assert isinstance(value, int)
    return value


def _json_list(response: httpx.Response) -> list[Mapping[str, object]]:
    payload = cast(object, json.loads(response.text))
    assert isinstance(payload, list)
    payload_items = cast(list[object], payload)
    typed_items: list[Mapping[str, object]] = []
    for item in payload_items:
        assert isinstance(item, dict)
        typed_items.append(cast(dict[str, object], item))
    return typed_items


def _create_category(
    httpx_client: httpx.Client, name: str, parent_id: int | None = None
) -> Mapping[str, object]:
    payload: dict[str, int | str] = {"name": name}
    if parent_id is not None:
        payload["parent_id"] = parent_id

    response = httpx_client.post("/api/categories", json=payload)
    assert response.status_code == 201
    return _json_object(response)


def _create_article(
    httpx_client: httpx.Client, category_id: int, title: str, body: str = ""
) -> Mapping[str, object]:
    response = httpx_client.post(
        f"/api/categories/{category_id}/articles",
        json={"title": title, "body": body},
    )
    assert response.status_code == 201
    return _json_object(response)


def test_create_category(httpx_client: httpx.Client) -> None:
    response = httpx_client.post("/api/categories", json={"name": "Databases"})

    assert response.status_code == 201
    payload = _json_object(response)
    assert payload["name"] == "Databases"
    assert payload["parent_id"] is None
    assert payload["is_deleted"] == 0


def test_create_subcategory(httpx_client: httpx.Client) -> None:
    parent = _create_category(httpx_client, "Programming")
    response = httpx_client.post(
        "/api/categories",
        json={"name": "Python", "parent_id": parent["id"]},
    )

    assert response.status_code == 201
    payload = _json_object(response)
    assert payload["name"] == "Python"
    assert payload["parent_id"] == parent["id"]


def test_list_categories_excludes_deleted(httpx_client: httpx.Client) -> None:
    category = _create_category(httpx_client, "Frameworks")
    delete_response = httpx_client.delete(f"/api/categories/{category['id']}")
    assert delete_response.status_code == 200

    list_response = httpx_client.get("/api/categories")
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_list_categories_include_deleted(httpx_client: httpx.Client) -> None:
    active = _create_category(httpx_client, "Active")
    deleted = _create_category(httpx_client, "Deleted")
    delete_response = httpx_client.delete(f"/api/categories/{deleted['id']}")
    assert delete_response.status_code == 200

    list_response = httpx_client.get("/api/categories?include_deleted=1")
    assert list_response.status_code == 200

    payload = _json_list(list_response)
    assert len(payload) == 2
    by_id = {_json_int(item, "id"): item for item in payload}
    assert by_id[_json_int(active, "id")]["is_deleted"] == 0
    assert by_id[_json_int(deleted, "id")]["is_deleted"] == 1


def test_get_category_with_children_and_articles(httpx_client: httpx.Client) -> None:
    parent = _create_category(httpx_client, "Backend")
    parent_id = _json_int(parent, "id")
    child = _create_category(httpx_client, "Flask", parent_id)
    article = _create_article(httpx_client, parent_id, "Routing Basics", "Body")

    detail_response = httpx_client.get(f"/api/categories/{parent_id}")
    assert detail_response.status_code == 200

    payload = _json_object(detail_response)
    assert payload["id"] == parent_id

    children_value = payload["children"]
    assert isinstance(children_value, list)
    children_list = cast(list[object], children_value)
    assert len(children_list) == 1
    child_payload: object = children_list[0]
    assert isinstance(child_payload, dict)
    assert child_payload["id"] == _json_int(child, "id")

    articles_value = payload["articles"]
    assert isinstance(articles_value, list)
    articles_list = cast(list[object], articles_value)
    assert len(articles_list) == 1
    article_payload: object = articles_list[0]
    assert isinstance(article_payload, dict)
    assert article_payload["id"] == _json_int(article, "id")


def test_soft_delete_cascades_to_articles(httpx_client: httpx.Client, app: Flask) -> None:
    category = _create_category(httpx_client, "ORM")
    category_id = _json_int(category, "id")
    article = _create_article(httpx_client, category_id, "Session Tips")

    delete_response = httpx_client.delete(f"/api/categories/{category_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["is_deleted"] == 1

    with app.app_context():
        db_category = db.session.get(Category, category_id)
        db_article = db.session.get(Article, _json_int(article, "id"))
        assert db_category is not None
        assert db_article is not None
        assert db_category.is_deleted == 1
        assert db_article.is_deleted == 1


def test_restore_category_restores_articles(httpx_client: httpx.Client, app: Flask) -> None:
    category = _create_category(httpx_client, "API")
    category_id = _json_int(category, "id")
    article = _create_article(httpx_client, category_id, "Status Codes")

    delete_response = httpx_client.delete(f"/api/categories/{category_id}")
    assert delete_response.status_code == 200

    restore_response = httpx_client.post(f"/api/categories/{category_id}/restore")
    assert restore_response.status_code == 200
    assert restore_response.json()["is_deleted"] == 0

    with app.app_context():
        db_category = db.session.get(Category, category_id)
        db_article = db.session.get(Article, _json_int(article, "id"))
        assert db_category is not None
        assert db_article is not None
        assert db_category.is_deleted == 0
        assert db_article.is_deleted == 0


def test_create_article(httpx_client: httpx.Client) -> None:
    category = _create_category(httpx_client, "SQL")

    response = httpx_client.post(
        f"/api/categories/{category['id']}/articles",
        json={"title": "Window Functions", "body": "Examples"},
    )

    assert response.status_code == 201
    payload = _json_object(response)
    assert payload["title"] == "Window Functions"
    assert payload["body"] == "Examples"
    assert payload["category_id"] == category["id"]
    assert payload["is_deleted"] == 0


def test_soft_delete_article(httpx_client: httpx.Client, app: Flask) -> None:
    category = _create_category(httpx_client, "Testing")
    category_id = _json_int(category, "id")
    article = _create_article(httpx_client, category_id, "Fixtures")
    article_id = _json_int(article, "id")

    delete_response = httpx_client.delete(f"/api/categories/{category_id}/articles/{article_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["is_deleted"] == 1

    list_response = httpx_client.get(f"/api/categories/{category_id}/articles")
    assert list_response.status_code == 200
    assert list_response.json() == []

    with app.app_context():
        db_article = db.session.get(Article, article_id)
        assert db_article is not None
        assert db_article.is_deleted == 1


def test_create_child_under_deleted_parent(httpx_client: httpx.Client) -> None:
    """Reject creating a child category under a deleted parent."""
    # Create parent
    parent_resp = httpx_client.post("/api/categories", json={"name": "Parent"})
    assert parent_resp.status_code == 201
    parent_id = _json_object(parent_resp)["id"]

    # Delete parent
    del_resp = httpx_client.delete(f"/api/categories/{parent_id}")
    assert del_resp.status_code == 200

    # Try to create child under deleted parent
    child_resp = httpx_client.post(
        "/api/categories", json={"name": "Child", "parent_id": parent_id}
    )
    assert child_resp.status_code == 400
    assert "deleted parent" in str(_json_object(child_resp).get("error", "")).lower()


def test_delete_category_with_active_children_returns_409(httpx_client: httpx.Client) -> None:
    parent = _create_category(httpx_client, "Parent")
    _ = _create_category(httpx_client, "Child", _json_int(parent, "id"))

    response = httpx_client.delete(f"/api/categories/{_json_int(parent, 'id')}")

    assert response.status_code == 409
    assert response.json() == {
        "error": "Cannot delete category with active children. Delete or reassign children first."
    }
