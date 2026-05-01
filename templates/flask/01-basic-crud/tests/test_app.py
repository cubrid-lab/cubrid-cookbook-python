# pyright: reportCallIssue=false
from __future__ import annotations

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import importlib

create_app = importlib.import_module("app").create_app


@pytest.fixture
def client(tmp_path: Path):
    database_path = tmp_path / "test.db"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        }
    )
    return app.test_client()


def test_api_list_products_returns_json_array(client) -> None:
    response = client.get("/api/products")
    assert response.status_code == 200
    assert response.get_json() == []


def test_api_crud_flow(client) -> None:
    create_response = client.post(
        "/api/products",
        json={
            "name": "Keyboard",
            "description": "TKL",
            "price": "99.99",
            "category": "Peripherals",
            "in_stock": 1,
        },
    )
    assert create_response.status_code == 201
    created = create_response.get_json()
    assert created["name"] == "Keyboard"
    assert created["price"] == "99.99"
    assert created["category"] == "Peripherals"

    product_id = created["id"]
    detail_response = client.get(f"/api/products/{product_id}")
    assert detail_response.status_code == 200
    assert detail_response.get_json()["description"] == "TKL"

    update_response = client.put(
        f"/api/products/{product_id}",
        json={"price": "109.99", "in_stock": 0},
    )
    assert update_response.status_code == 200
    updated = update_response.get_json()
    assert updated["price"] == "109.99"
    assert updated["in_stock"] == 0

    delete_response = client.delete(f"/api/products/{product_id}")
    assert delete_response.status_code == 200
    assert delete_response.get_json()["message"] == "Product deleted successfully."

    not_found_response = client.get(f"/api/products/{product_id}")
    assert not_found_response.status_code == 404
    assert not_found_response.get_json()["error"] == "Product not found."


def test_api_validation_errors(client) -> None:
    missing_name = client.post(
        "/api/products",
        json={
            "name": "",
            "description": "Test",
            "price": "10.00",
            "category": "General",
            "in_stock": 1,
        },
    )
    assert missing_name.status_code == 400
    assert missing_name.get_json()["error"] == "name is required"

    bad_price = client.post(
        "/api/products",
        json={
            "name": "Pen",
            "description": "Test",
            "price": "invalid",
            "category": "General",
            "in_stock": 1,
        },
    )
    assert bad_price.status_code == 400
    assert bad_price.get_json()["error"] == "Price must be a valid decimal number."


def test_api_update_not_found(client) -> None:
    response = client.put("/api/products/9999", json={"name": "Nope"})
    assert response.status_code == 404
    assert response.get_json()["error"] == "Product not found."


def test_api_list_contains_created_product(client) -> None:
    create_response = client.post(
        "/api/products",
        json={
            "name": "Monitor",
            "description": "27 inch",
            "price": "249.99",
            "category": "Displays",
            "in_stock": 1,
        },
    )
    assert create_response.status_code == 201

    response = client.get("/api/products")
    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload) == 1
    assert payload[0]["name"] == "Monitor"
    assert payload[0]["price"] == "249.99"
