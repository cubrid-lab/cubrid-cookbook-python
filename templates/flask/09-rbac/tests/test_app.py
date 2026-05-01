from __future__ import annotations

import importlib
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def client(tmp_path):
    create_app = importlib.import_module("app").create_app
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/test.db", "TESTING": True})
    with app.test_client() as c:
        yield c


def _create_user(client, user_key: str) -> None:
    response = client.post("/users", json={"user_key": user_key, "display_name": user_key})
    assert response.status_code == 201


def _upsert_role(
    client, role_key: str, name: str, parent_role_key=None, permissions=None, expected_version=None
):
    payload = {"name": name, "parent_role_key": parent_role_key, "permissions": permissions or []}
    if expected_version is not None:
        payload["expected_version"] = expected_version
    return client.put(f"/roles/{role_key}", json=payload)


def test_child_role_inherits_parent(client) -> None:
    _create_user(client, "alice")
    _create_user(client, "owner")

    parent = _upsert_role(client, "reader", "Reader", permissions=["document:read"])
    assert parent.status_code == 201
    child = _upsert_role(
        client, "writer", "Writer", parent_role_key="reader", permissions=["document:write"]
    )
    assert child.status_code == 201

    assign = client.post("/users/alice/roles/writer")
    assert assign.status_code == 201

    created = client.post(
        "/documents",
        json={
            "document_key": "doc-inherit",
            "owner_user_key": "owner",
            "title": "Title",
            "body_text": "Body",
            "as_user_key": "alice",
        },
    )
    assert created.status_code == 201

    fetched = client.get("/documents/doc-inherit?as_user_key=alice")
    assert fetched.status_code == 200
    assert fetched.get_json()["document_key"] == "doc-inherit"


def test_owner_access_without_role(client) -> None:
    _create_user(client, "owner")
    created = client.post(
        "/documents",
        json={
            "document_key": "doc-owner",
            "owner_user_key": "owner",
            "title": "OwnerTitle",
            "body_text": "Body",
            "as_user_key": "owner",
        },
    )
    assert created.status_code == 201

    read_response = client.get("/documents/doc-owner?as_user_key=owner")
    assert read_response.status_code == 200

    update_response = client.put(
        "/documents/doc-owner",
        json={
            "title": "Updated",
            "body_text": "Updated body",
            "as_user_key": "owner",
            "expected_version": 1,
        },
    )
    assert update_response.status_code == 200
    assert update_response.get_json()["version"] == 2


def test_non_owner_no_permission_403(client) -> None:
    _create_user(client, "owner")
    _create_user(client, "bob")
    created = client.post(
        "/documents",
        json={
            "document_key": "doc-private",
            "owner_user_key": "owner",
            "title": "Private",
            "body_text": "Hidden",
            "as_user_key": "owner",
        },
    )
    assert created.status_code == 201

    fetched = client.get("/documents/doc-private?as_user_key=bob")
    assert fetched.status_code == 403


def test_admin_wildcard_bypasses(client) -> None:
    _create_user(client, "owner")
    _create_user(client, "admin-user")

    admin_role = _upsert_role(client, "admin", "Admin", permissions=["admin:*"])
    assert admin_role.status_code == 201
    assign = client.post("/users/admin-user/roles/admin")
    assert assign.status_code == 201

    created = client.post(
        "/documents",
        json={
            "document_key": "doc-admin",
            "owner_user_key": "owner",
            "title": "Admin Write",
            "body_text": "Admin created this",
            "as_user_key": "admin-user",
        },
    )
    assert created.status_code == 201

    update_response = client.put(
        "/documents/doc-admin",
        json={
            "title": "Admin Updated",
            "body_text": "Updated",
            "as_user_key": "admin-user",
            "expected_version": 1,
        },
    )
    assert update_response.status_code == 200


def test_cycle_detection_400(client) -> None:
    create_a = _upsert_role(client, "a", "Role A", permissions=["document:read"])
    assert create_a.status_code == 201
    create_b = _upsert_role(client, "b", "Role B", parent_role_key="a", permissions=[])
    assert create_b.status_code == 201
    create_c = _upsert_role(client, "c", "Role C", parent_role_key="b", permissions=[])
    assert create_c.status_code == 201

    update_a = _upsert_role(
        client,
        "a",
        "Role A",
        parent_role_key="c",
        permissions=["document:read"],
        expected_version=1,
    )
    assert update_a.status_code == 400


def test_concurrent_document_update_409(client) -> None:
    _create_user(client, "owner")
    created = client.post(
        "/documents",
        json={
            "document_key": "doc-version",
            "owner_user_key": "owner",
            "title": "Versioned",
            "body_text": "Body",
            "as_user_key": "owner",
        },
    )
    assert created.status_code == 201

    first_update = client.put(
        "/documents/doc-version",
        json={"title": "v2", "body_text": "v2", "as_user_key": "owner", "expected_version": 1},
    )
    assert first_update.status_code == 200

    stale_update = client.put(
        "/documents/doc-version",
        json={"title": "v3", "body_text": "v3", "as_user_key": "owner", "expected_version": 1},
    )
    assert stale_update.status_code == 409


def test_duplicate_role_assignment_409(client) -> None:
    _create_user(client, "alice")
    role = _upsert_role(client, "reader", "Reader", permissions=["document:read"])
    assert role.status_code == 201

    first = client.post("/users/alice/roles/reader")
    assert first.status_code == 201
    second = client.post("/users/alice/roles/reader")
    assert second.status_code == 409
