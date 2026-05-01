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

class SupplierPayload(TypedDict):
    id: int
    name: str
    code: str


class PurchaseOrderLinePayload(TypedDict):
    id: int
    order_id: int
    sku: str
    description: str
    quantity: int
    unit_cost: int
    received_qty: int


class PurchaseOrderPayload(TypedDict):
    id: int
    supplier_id: int
    status: str
    notes: str | None
    lines: list[PurchaseOrderLinePayload]


def _create_supplier(httpx_client: httpx.Client, code: str = "SUP-001") -> SupplierPayload:
    response = httpx_client.post(
        "/api/suppliers",
        json={"name": "Acme Supply", "code": code},
    )
    assert response.status_code == 201
    return cast(SupplierPayload, response.json())


def _create_purchase_order(
    httpx_client: httpx.Client,
    supplier_id: int,
    lines: list[dict[str, object]],
    notes: str | None = None,
) -> PurchaseOrderPayload:
    payload: dict[str, object] = {"supplier_id": supplier_id, "lines": lines}
    if notes is not None:
        payload["notes"] = notes

    response = httpx_client.post("/api/purchase-orders", json=payload)
    assert response.status_code == 201
    return cast(PurchaseOrderPayload, response.json())


def test_create_supplier(httpx_client: httpx.Client) -> None:
    response = httpx_client.post(
        "/api/suppliers",
        json={"name": "Global Parts", "code": "SUP-GLB"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Global Parts"
    assert payload["code"] == "SUP-GLB"


def test_create_purchase_order_with_lines(httpx_client: httpx.Client) -> None:
    supplier = _create_supplier(httpx_client)

    response = httpx_client.post(
        "/api/purchase-orders",
        json={
            "supplier_id": supplier["id"],
            "notes": "Urgent replenishment",
            "lines": [
                {
                    "sku": "SKU-100",
                    "description": "Keyboard",
                    "quantity": 5,
                    "unit_cost": 12999,
                },
                {
                    "sku": "SKU-200",
                    "description": "Mouse",
                    "quantity": 10,
                    "unit_cost": 4999,
                },
            ],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["supplier_id"] == supplier["id"]
    assert payload["status"] == "draft"
    assert payload["notes"] == "Urgent replenishment"
    assert len(payload["lines"]) == 2
    assert payload["lines"][0]["received_qty"] == 0


def test_submit_purchase_order(httpx_client: httpx.Client) -> None:
    supplier = _create_supplier(httpx_client)
    order = _create_purchase_order(
        httpx_client,
        supplier["id"],
        [{"sku": "SKU-A", "description": "Adapter", "quantity": 2, "unit_cost": 1500}],
    )

    response = httpx_client.post(f"/api/purchase-orders/{order['id']}/submit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "submitted"
    assert payload["submitted_at"] is not None


def test_submit_without_lines_rejected(httpx_client: httpx.Client) -> None:
    supplier = _create_supplier(httpx_client)
    order = _create_purchase_order(httpx_client, supplier["id"], [])

    response = httpx_client.post(f"/api/purchase-orders/{order['id']}/submit")

    assert response.status_code == 400
    assert response.json()["error"] == "Cannot submit purchase order without lines."


def test_approve_purchase_order(httpx_client: httpx.Client) -> None:
    supplier = _create_supplier(httpx_client)
    order = _create_purchase_order(
        httpx_client,
        supplier["id"],
        [{"sku": "SKU-B", "description": "Battery", "quantity": 4, "unit_cost": 2200}],
    )

    submit_response = httpx_client.post(f"/api/purchase-orders/{order['id']}/submit")
    assert submit_response.status_code == 200

    approve_response = httpx_client.post(f"/api/purchase-orders/{order['id']}/approve")

    assert approve_response.status_code == 200
    payload = approve_response.json()
    assert payload["status"] == "approved"
    assert payload["approved_at"] is not None


def test_invalid_transition_409(httpx_client: httpx.Client) -> None:
    supplier = _create_supplier(httpx_client)
    order = _create_purchase_order(
        httpx_client,
        supplier["id"],
        [{"sku": "SKU-C", "description": "Cable", "quantity": 1, "unit_cost": 999}],
    )

    response = httpx_client.post(f"/api/purchase-orders/{order['id']}/approve")

    assert response.status_code == 409
    assert response.json()["error"] == "Invalid transition: draft -> approved"


def test_receive_partial(httpx_client: httpx.Client) -> None:
    supplier = _create_supplier(httpx_client)
    order = _create_purchase_order(
        httpx_client,
        supplier["id"],
        [{"sku": "SKU-D", "description": "Dock", "quantity": 8, "unit_cost": 8999}],
    )

    submit_response = httpx_client.post(f"/api/purchase-orders/{order['id']}/submit")
    assert submit_response.status_code == 200
    approve_response = httpx_client.post(f"/api/purchase-orders/{order['id']}/approve")
    assert approve_response.status_code == 200

    line_id = order["lines"][0]["id"]
    receive_response = httpx_client.post(
        f"/api/purchase-orders/{order['id']}/receive",
        json={"lines": [{"line_id": line_id, "qty_received": 3}]},
    )

    assert receive_response.status_code == 200
    payload = receive_response.json()
    assert payload["status"] == "approved"
    assert payload["lines"][0]["received_qty"] == 3


def test_receive_full_auto_fulfills(httpx_client: httpx.Client) -> None:
    supplier = _create_supplier(httpx_client)
    order = _create_purchase_order(
        httpx_client,
        supplier["id"],
        [
            {"sku": "SKU-E1", "description": "SSD", "quantity": 2, "unit_cost": 7500},
            {"sku": "SKU-E2", "description": "RAM", "quantity": 3, "unit_cost": 4200},
        ],
    )

    submit_response = httpx_client.post(f"/api/purchase-orders/{order['id']}/submit")
    assert submit_response.status_code == 200
    approve_response = httpx_client.post(f"/api/purchase-orders/{order['id']}/approve")
    assert approve_response.status_code == 200

    line_1 = order["lines"][0]["id"]
    line_2 = order["lines"][1]["id"]
    receive_response = httpx_client.post(
        f"/api/purchase-orders/{order['id']}/receive",
        json={
            "lines": [
                {"line_id": line_1, "qty_received": 2},
                {"line_id": line_2, "qty_received": 3},
            ]
        },
    )

    assert receive_response.status_code == 200
    payload = receive_response.json()
    assert payload["status"] == "fulfilled"
    assert payload["fulfilled_at"] is not None


def test_over_receive_rejected(httpx_client: httpx.Client) -> None:
    supplier = _create_supplier(httpx_client)
    order = _create_purchase_order(
        httpx_client,
        supplier["id"],
        [{"sku": "SKU-F", "description": "Fan", "quantity": 4, "unit_cost": 1999}],
    )

    submit_response = httpx_client.post(f"/api/purchase-orders/{order['id']}/submit")
    assert submit_response.status_code == 200
    approve_response = httpx_client.post(f"/api/purchase-orders/{order['id']}/approve")
    assert approve_response.status_code == 200

    line_id = order["lines"][0]["id"]
    receive_response = httpx_client.post(
        f"/api/purchase-orders/{order['id']}/receive",
        json={"lines": [{"line_id": line_id, "qty_received": 5}]},
    )

    assert receive_response.status_code == 400
    assert receive_response.json()["error"] == "Cannot receive more than ordered quantity."


def test_cancel_from_draft(httpx_client: httpx.Client) -> None:
    supplier = _create_supplier(httpx_client)
    order = _create_purchase_order(
        httpx_client,
        supplier["id"],
        [{"sku": "SKU-G", "description": "GPU", "quantity": 1, "unit_cost": 39900}],
    )

    response = httpx_client.post(f"/api/purchase-orders/{order['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_from_approved_rejected(httpx_client: httpx.Client) -> None:
    supplier = _create_supplier(httpx_client)
    order = _create_purchase_order(
        httpx_client,
        supplier["id"],
        [{"sku": "SKU-H", "description": "Hub", "quantity": 6, "unit_cost": 2500}],
    )

    submit_response = httpx_client.post(f"/api/purchase-orders/{order['id']}/submit")
    assert submit_response.status_code == 200
    approve_response = httpx_client.post(f"/api/purchase-orders/{order['id']}/approve")
    assert approve_response.status_code == 200

    response = httpx_client.post(f"/api/purchase-orders/{order['id']}/cancel")

    assert response.status_code == 409
    assert response.json()["error"] == "Invalid transition: approved -> cancelled"
