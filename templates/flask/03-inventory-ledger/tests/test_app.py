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
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        yield client


class WarehousePayload(TypedDict):
    id: int
    code: str
    name: str


class StockItemPayload(TypedDict):
    id: int
    warehouse_id: int
    sku: str
    product_name: str
    on_hand_qty: int


def _create_warehouse(httpx_client: httpx.Client, code: str, name: str) -> WarehousePayload:
    response = httpx_client.post("/api/inventory/warehouses", json={"code": code, "name": name})
    assert response.status_code == 201
    return cast(WarehousePayload, response.json())


def _create_item(
    httpx_client: httpx.Client,
    warehouse_id: int,
    sku: str,
    product_name: str,
    on_hand_qty: int = 0,
) -> StockItemPayload:
    response = httpx_client.post(
        "/api/inventory/items",
        json={
            "warehouse_id": warehouse_id,
            "sku": sku,
            "product_name": product_name,
            "on_hand_qty": on_hand_qty,
        },
    )
    assert response.status_code == 201
    return cast(StockItemPayload, response.json())


def test_create_warehouse(httpx_client: httpx.Client) -> None:
    response = httpx_client.post(
        "/api/inventory/warehouses",
        json={"code": "WH-SEA", "name": "Seattle Warehouse"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["code"] == "WH-SEA"
    assert payload["name"] == "Seattle Warehouse"


def test_create_stock_item(httpx_client: httpx.Client) -> None:
    warehouse = _create_warehouse(httpx_client, "WH-A", "Warehouse A")

    response = httpx_client.post(
        "/api/inventory/items",
        json={
            "warehouse_id": warehouse["id"],
            "sku": "SKU-100",
            "product_name": "Widget",
            "on_hand_qty": 5,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["warehouse_id"] == warehouse["id"]
    assert payload["sku"] == "SKU-100"
    assert payload["product_name"] == "Widget"
    assert payload["on_hand_qty"] == 5


def test_adjust_stock_positive(httpx_client: httpx.Client) -> None:
    warehouse = _create_warehouse(httpx_client, "WH-B", "Warehouse B")
    item = _create_item(
        httpx_client,
        warehouse_id=warehouse["id"],
        sku="SKU-ADJ",
        product_name="Adjustable Item",
        on_hand_qty=0,
    )

    response = httpx_client.post(
        "/api/inventory/adjustments",
        json={"stock_item_id": item["id"], "qty_delta": 10, "note": "initial receipt"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["item"]["on_hand_qty"] == 10
    assert payload["movement"]["movement_type"] == "adjustment"
    assert payload["movement"]["qty_delta"] == 10


def test_adjust_stock_negative_insufficient(httpx_client: httpx.Client) -> None:
    warehouse = _create_warehouse(httpx_client, "WH-C", "Warehouse C")
    item = _create_item(
        httpx_client,
        warehouse_id=warehouse["id"],
        sku="SKU-LOW",
        product_name="Low Stock Item",
        on_hand_qty=0,
    )

    response = httpx_client.post(
        "/api/inventory/adjustments",
        json={"stock_item_id": item["id"], "qty_delta": -999, "note": "bad adjustment"},
    )

    assert response.status_code == 409
    assert response.json()["error"] == "Insufficient stock for adjustment."


def test_transfer_success(httpx_client: httpx.Client) -> None:
    from_warehouse = _create_warehouse(httpx_client, "WH-FROM", "From Warehouse")
    to_warehouse = _create_warehouse(httpx_client, "WH-TO", "To Warehouse")

    from_item = _create_item(
        httpx_client,
        warehouse_id=from_warehouse["id"],
        sku="SKU-XFER",
        product_name="Transfer Item",
        on_hand_qty=20,
    )
    to_item = _create_item(
        httpx_client,
        warehouse_id=to_warehouse["id"],
        sku="SKU-XFER",
        product_name="Transfer Item",
        on_hand_qty=1,
    )

    response = httpx_client.post(
        "/api/inventory/transfers",
        json={
            "from_item_id": from_item["id"],
            "to_item_id": to_item["id"],
            "quantity": 7,
            "note": "rebalance",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["from_item"]["on_hand_qty"] == 13
    assert payload["to_item"]["on_hand_qty"] == 8
    assert len(payload["movements"]) == 2
    assert payload["movements"][0]["movement_type"] == "transfer_out"
    assert payload["movements"][0]["qty_delta"] == -7
    assert payload["movements"][1]["movement_type"] == "transfer_in"
    assert payload["movements"][1]["qty_delta"] == 7
    assert payload["movements"][0]["reference"] == payload["movements"][1]["reference"]


def test_transfer_insufficient_stock(httpx_client: httpx.Client) -> None:
    from_warehouse = _create_warehouse(httpx_client, "WH-FROM2", "From Warehouse 2")
    to_warehouse = _create_warehouse(httpx_client, "WH-TO2", "To Warehouse 2")

    from_item = _create_item(
        httpx_client,
        warehouse_id=from_warehouse["id"],
        sku="SKU-FAIL",
        product_name="Fail Item",
        on_hand_qty=3,
    )
    to_item = _create_item(
        httpx_client,
        warehouse_id=to_warehouse["id"],
        sku="SKU-FAIL",
        product_name="Fail Item",
        on_hand_qty=0,
    )

    response = httpx_client.post(
        "/api/inventory/transfers",
        json={
            "from_item_id": from_item["id"],
            "to_item_id": to_item["id"],
            "quantity": 99,
            "note": "too much",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"] == "Insufficient stock for transfer."

    from_item_detail = httpx_client.get(f"/api/inventory/items/{from_item['id']}")
    to_item_detail = httpx_client.get(f"/api/inventory/items/{to_item['id']}")
    assert from_item_detail.status_code == 200
    assert to_item_detail.status_code == 200
    assert from_item_detail.json()["on_hand_qty"] == 3
    assert to_item_detail.json()["on_hand_qty"] == 0
    assert from_item_detail.json()["movements"] == []
    assert to_item_detail.json()["movements"] == []


def test_movements_history(httpx_client: httpx.Client) -> None:
    from_warehouse = _create_warehouse(httpx_client, "WH-H1", "History 1")
    to_warehouse = _create_warehouse(httpx_client, "WH-H2", "History 2")

    from_item = _create_item(
        httpx_client,
        warehouse_id=from_warehouse["id"],
        sku="SKU-HIST",
        product_name="History Item",
        on_hand_qty=5,
    )
    to_item = _create_item(
        httpx_client,
        warehouse_id=to_warehouse["id"],
        sku="SKU-HIST",
        product_name="History Item",
        on_hand_qty=0,
    )

    adjustment_response = httpx_client.post(
        "/api/inventory/adjustments",
        json={"stock_item_id": from_item["id"], "qty_delta": 10, "note": "receipt"},
    )
    assert adjustment_response.status_code == 200

    transfer_response = httpx_client.post(
        "/api/inventory/transfers",
        json={
            "from_item_id": from_item["id"],
            "to_item_id": to_item["id"],
            "quantity": 4,
            "note": "history transfer",
        },
    )
    assert transfer_response.status_code == 200

    movement_response = httpx_client.get(f"/api/inventory/items/{from_item['id']}/movements")
    assert movement_response.status_code == 200
    movement_payload = movement_response.json()
    assert len(movement_payload) == 2
    assert movement_payload[0]["movement_type"] == "transfer_out"
    assert movement_payload[0]["qty_delta"] == -4
    assert movement_payload[1]["movement_type"] == "adjustment"
    assert movement_payload[1]["qty_delta"] == 10


def test_list_items_filter_by_warehouse(httpx_client: httpx.Client) -> None:
    warehouse_1 = _create_warehouse(httpx_client, "WH-F1", "Filter 1")
    warehouse_2 = _create_warehouse(httpx_client, "WH-F2", "Filter 2")

    _ = _create_item(
        httpx_client,
        warehouse_id=warehouse_1["id"],
        sku="SKU-F1",
        product_name="Filter One",
        on_hand_qty=1,
    )
    _ = _create_item(
        httpx_client,
        warehouse_id=warehouse_2["id"],
        sku="SKU-F2",
        product_name="Filter Two",
        on_hand_qty=2,
    )

    response = httpx_client.get(f"/api/inventory/items?warehouse_id={warehouse_1['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["warehouse_id"] == warehouse_1["id"]
    assert payload[0]["sku"] == "SKU-F1"


def test_duplicate_warehouse_code_returns_409(httpx_client: httpx.Client) -> None:
    """Duplicate warehouse code returns 409."""
    payload = {"code": "DUP-WH", "name": "Warehouse A"}
    resp1 = httpx_client.post("/api/inventory/warehouses", json=payload)
    assert resp1.status_code == 201

    resp2 = httpx_client.post("/api/inventory/warehouses", json=payload)
    assert resp2.status_code == 409


def test_duplicate_sku_in_warehouse_returns_409(httpx_client: httpx.Client) -> None:
    """Duplicate SKU in same warehouse returns 409."""
    wh = httpx_client.post(
        "/api/inventory/warehouses", json={"code": "WH-SKU", "name": "Test"}
    ).json()
    item_payload = {"warehouse_id": wh["id"], "sku": "SAME-SKU", "product_name": "Widget"}
    resp1 = httpx_client.post("/api/inventory/items", json=item_payload)
    assert resp1.status_code == 201

    resp2 = httpx_client.post("/api/inventory/items", json=item_payload)
    assert resp2.status_code == 409


def test_transfer_different_sku_rejected(httpx_client: httpx.Client) -> None:
    """Transfer between items with different SKUs is rejected."""
    wh = httpx_client.post(
        "/api/inventory/warehouses", json={"code": "WH-XSKU", "name": "X"}
    ).json()
    item_a = httpx_client.post(
        "/api/inventory/items",
        json={"warehouse_id": wh["id"], "sku": "SKU-A", "product_name": "A", "on_hand_qty": 10},
    ).json()
    item_b = httpx_client.post(
        "/api/inventory/items",
        json={"warehouse_id": wh["id"], "sku": "SKU-B", "product_name": "B", "on_hand_qty": 5},
    ).json()

    resp = httpx_client.post(
        "/api/inventory/transfers",
        json={"from_item_id": item_a["id"], "to_item_id": item_b["id"], "quantity": 2},
    )
    assert resp.status_code == 400
    assert "different SKU" in resp.json()["error"]
