# pyright: reportCallIssue=false
from __future__ import annotations

from pathlib import Path
import sys
from typing import TypedDict, cast

import httpx
import pytest
from flask import Flask
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import importlib

create_app = importlib.import_module("app").create_app
db = importlib.import_module("database").db
_models = importlib.import_module("models")
BatchProduct = _models.BatchProduct


@pytest.fixture
def app(tmp_path: Path):
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}", "SQLALCHEMY_TRACK_MODIFICATIONS": False})


@pytest.fixture
def httpx_client(app):
    transport = httpx.WSGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        yield client

class BatchProductPayload(TypedDict):
    id: int
    sku: str
    name: str
    price: int
    is_active: int


def _seed_products(httpx_client: httpx.Client) -> None:
    response = httpx_client.post(
        "/api/batch/products/seed",
        json={
            "products": [
                {"sku": "SKU-100", "name": "Keyboard", "price": 10000},
                {"sku": "SKU-200", "name": "Mouse", "price": 5000},
                {"sku": "SKU-300", "name": "Monitor", "price": 30000},
            ]
        },
    )
    assert response.status_code == 201


def _list_products(httpx_client: httpx.Client) -> list[BatchProductPayload]:
    response = httpx_client.get("/api/batch/products")
    assert response.status_code == 200
    return cast(list[BatchProductPayload], response.json())


def test_seed_products(httpx_client: httpx.Client) -> None:
    _seed_products(httpx_client)
    products = _list_products(httpx_client)
    assert len(products) == 3
    assert products[0]["sku"] == "SKU-100"
    assert products[1]["sku"] == "SKU-200"
    assert products[2]["sku"] == "SKU-300"


def test_batch_price_update_all_success(httpx_client: httpx.Client) -> None:
    _seed_products(httpx_client)
    response = httpx_client.post(
        "/api/batch/jobs/price-update",
        json={
            "updates": [
                {"sku": "SKU-100", "new_price": 12000},
                {"sku": "SKU-200", "new_price": 6500},
            ]
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["total_rows"] == 2
    assert payload["success_cnt"] == 2
    assert payload["failed_cnt"] == 0
    assert payload["errors"] == []


def test_batch_price_update_partial_failure(httpx_client: httpx.Client) -> None:
    _seed_products(httpx_client)
    response = httpx_client.post(
        "/api/batch/jobs/price-update",
        json={
            "updates": [
                {"sku": "SKU-100", "new_price": 11000},
                {"sku": "SKU-999", "new_price": 7000},
            ]
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["success_cnt"] == 1
    assert payload["failed_cnt"] == 1
    assert len(payload["errors"]) == 1
    assert payload["errors"][0]["sku"] == "SKU-999"


def test_batch_price_update_invalid_price(httpx_client: httpx.Client) -> None:
    _seed_products(httpx_client)
    response = httpx_client.post(
        "/api/batch/jobs/price-update",
        json={"updates": [{"sku": "SKU-100", "new_price": -5}]},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["success_cnt"] == 0
    assert payload["failed_cnt"] == 1
    assert payload["errors"][0]["error"] == "new_price must be a positive integer"


def test_batch_empty_updates_rejected(httpx_client: httpx.Client) -> None:
    response = httpx_client.post("/api/batch/jobs/price-update", json={"updates": []})
    assert response.status_code == 400
    assert response.json()["error"] == "updates cannot be empty"


def test_get_job_with_rows(httpx_client: httpx.Client) -> None:
    _seed_products(httpx_client)
    create_response = httpx_client.post(
        "/api/batch/jobs/price-update",
        json={
            "updates": [
                {"sku": "SKU-100", "new_price": 15000},
                {"sku": "SKU-404", "new_price": 23000},
            ]
        },
    )
    assert create_response.status_code == 201
    job_id = create_response.json()["job_id"]

    response = httpx_client.get(f"/api/batch/jobs/{job_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == job_id
    assert len(payload["rows"]) == 2
    assert payload["rows"][0]["row_index"] == 1
    assert payload["rows"][1]["row_index"] == 2


def test_list_jobs(httpx_client: httpx.Client) -> None:
    _seed_products(httpx_client)
    response_1 = httpx_client.post(
        "/api/batch/jobs/price-update",
        json={"updates": [{"sku": "SKU-100", "new_price": 10001}]},
    )
    assert response_1.status_code == 201

    response_2 = httpx_client.post(
        "/api/batch/jobs/price-update",
        json={"updates": [{"sku": "SKU-200", "new_price": 5001}]},
    )
    assert response_2.status_code == 201

    response = httpx_client.get("/api/batch/jobs")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["job_type"] == "price_update"
    assert payload[1]["job_type"] == "price_update"


def test_products_updated_after_batch(httpx_client: httpx.Client, app: Flask) -> None:
    _seed_products(httpx_client)
    response = httpx_client.post(
        "/api/batch/jobs/price-update",
        json={
            "updates": [
                {"sku": "SKU-100", "new_price": 19999},
                {"sku": "SKU-200", "new_price": 7999},
            ]
        },
    )
    assert response.status_code == 201

    with app.app_context():
        product_1 = db.session.execute(
            select(BatchProduct).where(BatchProduct.sku == "SKU-100")
        ).scalar_one()
        product_2 = db.session.execute(
            select(BatchProduct).where(BatchProduct.sku == "SKU-200")
        ).scalar_one()
        assert product_1.price == 19999
        assert product_2.price == 7999
