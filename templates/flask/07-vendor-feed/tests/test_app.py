# pyright: reportCallIssue=false
from __future__ import annotations

from pathlib import Path
import sys
from typing import TypedDict, cast

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import importlib

create_app = importlib.import_module("app").create_app


@pytest.fixture
def app(tmp_path: Path):
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}", "SQLALCHEMY_TRACK_MODIFICATIONS": False})


@pytest.fixture
def httpx_client(app):
    transport = httpx.WSGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        yield client

class ImportBatchPayload(TypedDict):
    id: int
    vendor_name: str
    source_filename: str
    status: str


def _create_batch(
    httpx_client: httpx.Client,
    vendor_name: str = "acme",
    source_filename: str = "feed.csv",
) -> ImportBatchPayload:
    response = httpx_client.post(
        "/api/imports",
        json={"vendor_name": vendor_name, "source_filename": source_filename},
    )
    assert response.status_code == 201
    return cast(ImportBatchPayload, response.json())


def _add_rows(httpx_client: httpx.Client, batch_id: int, rows: list[dict[str, object]]) -> None:
    response = httpx_client.post(f"/api/imports/{batch_id}/rows", json={"rows": rows})
    assert response.status_code == 201


def _validate_batch(httpx_client: httpx.Client, batch_id: int) -> dict[str, object]:
    response = httpx_client.post(f"/api/imports/{batch_id}/validate")
    assert response.status_code == 200
    return cast(dict[str, object], response.json())


def _promote_batch(httpx_client: httpx.Client, batch_id: int) -> dict[str, object]:
    response = httpx_client.post(f"/api/imports/{batch_id}/promote")
    assert response.status_code == 200
    return cast(dict[str, object], response.json())


def test_create_batch_and_add_rows(httpx_client: httpx.Client) -> None:
    batch = _create_batch(httpx_client)
    _add_rows(
        httpx_client,
        batch["id"],
        [
            {
                "row_no": 1,
                "external_sku": "SKU-100",
                "name": "Keyboard",
                "price_cents": 10000,
                "raw_payload": '{"sku":"SKU-100"}',
            },
            {
                "row_no": 2,
                "external_sku": "SKU-200",
                "name": "Mouse",
                "price_cents": 5000,
                "raw_payload": '{"sku":"SKU-200"}',
            },
        ],
    )

    detail_response = httpx_client.get(f"/api/imports/{batch['id']}")
    assert detail_response.status_code == 200
    payload = cast(dict[str, object], detail_response.json())
    assert payload["status"] == "uploaded"
    rows = cast(list[dict[str, object]], payload["rows"])
    assert len(rows) == 2
    assert rows[0]["row_no"] == 1


def test_validate_marks_valid_and_invalid_rows(httpx_client: httpx.Client) -> None:
    batch = _create_batch(httpx_client)
    _add_rows(
        httpx_client,
        batch["id"],
        [
            {
                "row_no": 1,
                "external_sku": "SKU-100",
                "name": "Keyboard",
                "price_cents": 12000,
                "raw_payload": "ok",
            },
            {
                "row_no": 2,
                "external_sku": "",
                "name": "",
                "price_cents": 0,
                "raw_payload": "bad",
            },
        ],
    )

    summary = _validate_batch(httpx_client, batch["id"])
    assert summary["status"] == "validated"
    assert summary["valid_rows"] == 1
    assert summary["invalid_rows"] == 1

    detail_response = httpx_client.get(f"/api/imports/{batch['id']}")
    assert detail_response.status_code == 200
    detail_payload = cast(dict[str, object], detail_response.json())
    rows = cast(list[dict[str, object]], detail_payload["rows"])
    assert rows[0]["validation_status"] == "valid"
    assert rows[0]["error_code"] is None
    assert rows[1]["validation_status"] == "invalid"
    assert rows[1]["error_code"] is not None
    assert rows[1]["error_message"] is not None


def test_promote_creates_catalog_products(httpx_client: httpx.Client) -> None:
    batch = _create_batch(httpx_client, vendor_name="vendor-a")
    _add_rows(
        httpx_client,
        batch["id"],
        [
            {
                "row_no": 1,
                "external_sku": "SKU-100",
                "name": "Keyboard",
                "price_cents": 10000,
                "raw_payload": "ok",
            }
        ],
    )
    _ = _validate_batch(httpx_client, batch["id"])
    promote_summary = _promote_batch(httpx_client, batch["id"])

    assert promote_summary["status"] == "promoted"
    assert promote_summary["promoted_rows"] == 1

    products_response = httpx_client.get("/api/products?vendor_name=vendor-a")
    assert products_response.status_code == 200
    products = cast(list[dict[str, object]], products_response.json())
    assert len(products) == 1
    assert products[0]["external_sku"] == "SKU-100"
    assert products[0]["price_cents"] == 10000


def test_promote_upsert_updates_existing_product(httpx_client: httpx.Client) -> None:
    first_batch = _create_batch(
        httpx_client, vendor_name="vendor-upsert", source_filename="first.csv"
    )
    _add_rows(
        httpx_client,
        first_batch["id"],
        [
            {
                "row_no": 1,
                "external_sku": "SKU-500",
                "name": "Name A",
                "price_cents": 1111,
                "raw_payload": "first",
            }
        ],
    )
    _ = _validate_batch(httpx_client, first_batch["id"])
    _ = _promote_batch(httpx_client, first_batch["id"])

    second_batch = _create_batch(
        httpx_client, vendor_name="vendor-upsert", source_filename="second.csv"
    )
    _add_rows(
        httpx_client,
        second_batch["id"],
        [
            {
                "row_no": 1,
                "external_sku": "SKU-500",
                "name": "Name B",
                "price_cents": 2222,
                "raw_payload": "second",
            }
        ],
    )
    _ = _validate_batch(httpx_client, second_batch["id"])
    _ = _promote_batch(httpx_client, second_batch["id"])

    products_response = httpx_client.get("/api/products?vendor_name=vendor-upsert")
    assert products_response.status_code == 200
    products = cast(list[dict[str, object]], products_response.json())
    assert len(products) == 1
    assert products[0]["name"] == "Name B"
    assert products[0]["price_cents"] == 2222


def test_reject_promote_if_not_validated(httpx_client: httpx.Client) -> None:
    batch = _create_batch(httpx_client)
    _add_rows(
        httpx_client,
        batch["id"],
        [
            {
                "row_no": 1,
                "external_sku": "SKU-100",
                "name": "Keyboard",
                "price_cents": 10000,
                "raw_payload": "ok",
            }
        ],
    )

    response = httpx_client.post(f"/api/imports/{batch['id']}/promote")
    assert response.status_code == 409


def test_reject_double_promote(httpx_client: httpx.Client) -> None:
    batch = _create_batch(httpx_client)
    _add_rows(
        httpx_client,
        batch["id"],
        [
            {
                "row_no": 1,
                "external_sku": "SKU-777",
                "name": "Dock",
                "price_cents": 3300,
                "raw_payload": "ok",
            }
        ],
    )
    _ = _validate_batch(httpx_client, batch["id"])
    _ = _promote_batch(httpx_client, batch["id"])

    second_response = httpx_client.post(f"/api/imports/{batch['id']}/promote")
    assert second_response.status_code == 409


def test_invalid_rows_skipped_during_promote(httpx_client: httpx.Client) -> None:
    batch = _create_batch(httpx_client, vendor_name="vendor-skip")
    _add_rows(
        httpx_client,
        batch["id"],
        [
            {
                "row_no": 1,
                "external_sku": "SKU-OK",
                "name": "Valid",
                "price_cents": 1000,
                "raw_payload": "ok",
            },
            {
                "row_no": 2,
                "external_sku": "SKU-BAD",
                "name": "",
                "price_cents": 0,
                "raw_payload": "bad",
            },
        ],
    )
    _ = _validate_batch(httpx_client, batch["id"])

    promote_summary = _promote_batch(httpx_client, batch["id"])
    assert promote_summary["promoted_rows"] == 1
    assert promote_summary["skipped_rows"] == 1

    products_response = httpx_client.get("/api/products?vendor_name=vendor-skip")
    assert products_response.status_code == 200
    products = cast(list[dict[str, object]], products_response.json())
    assert len(products) == 1
    assert products[0]["external_sku"] == "SKU-OK"
