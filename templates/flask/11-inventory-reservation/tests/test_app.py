from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, update

from app import create_app  # pyright: ignore[reportImplicitRelativeImport]
from database import db  # pyright: ignore[reportImplicitRelativeImport]
from models import InventoryItem, StockReservation  # pyright: ignore[reportImplicitRelativeImport]


@pytest.fixture
def client(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/test.db", "TESTING": True})
    with app.test_client() as c:
        yield c


def _create_item(client, sku="SKU-1", qty=10):
    response = client.post("/items", json={"sku": sku, "name": f"Item {sku}", "on_hand_qty": qty})
    assert response.status_code == 201
    return response.get_json()


def _create_reservation(client, reservation_key="res-1", sku="SKU-1", quantity=3, ttl_seconds=60):
    response = client.post(
        "/reservations",
        json={
            "reservation_key": reservation_key,
            "sku": sku,
            "client_id": "client-1",
            "quantity": quantity,
            "ttl_seconds": ttl_seconds,
        },
    )
    return response


def test_reserve_success(client):
    _create_item(client, sku="SKU-OK", qty=10)
    response = _create_reservation(client, reservation_key="res-ok", sku="SKU-OK", quantity=4)
    assert response.status_code == 201

    item_response = client.get("/items/SKU-OK")
    assert item_response.status_code == 200
    item = item_response.get_json()
    assert item["reserved_qty"] == 4
    assert item["available_qty"] == 6


def test_over_reserve_422(client):
    _create_item(client, sku="SKU-LOW", qty=5)
    response = _create_reservation(client, reservation_key="res-low", sku="SKU-LOW", quantity=6)
    assert response.status_code == 422


def test_confirm_active(client):
    _create_item(client, sku="SKU-CF", qty=10)
    response = _create_reservation(client, reservation_key="res-cf", sku="SKU-CF", quantity=3)
    assert response.status_code == 201

    confirm_response = client.post("/reservations/res-cf/confirm")
    assert confirm_response.status_code == 200
    reservation = confirm_response.get_json()
    assert reservation["state"] == "confirmed"

    item_response = client.get("/items/SKU-CF")
    item = item_response.get_json()
    assert item["reserved_qty"] == 0
    assert item["committed_qty"] == 3
    assert item["available_qty"] == 7


def test_confirm_expired_422(client):
    _create_item(client, sku="SKU-EX", qty=10)
    response = _create_reservation(
        client, reservation_key="res-ex", sku="SKU-EX", quantity=2, ttl_seconds=1
    )
    assert response.status_code == 201

    with client.application.app_context():
        db.session.execute(
            update(StockReservation)
            .where(StockReservation.reservation_key == "res-ex")
            .values(expires_at=datetime.utcnow() - timedelta(seconds=1))
        )
        db.session.commit()

    confirm_response = client.post("/reservations/res-ex/confirm")
    assert confirm_response.status_code == 422


def test_cancel_restores_stock(client):
    _create_item(client, sku="SKU-CA", qty=8)
    response = _create_reservation(client, reservation_key="res-ca", sku="SKU-CA", quantity=5)
    assert response.status_code == 201

    cancel_response = client.post("/reservations/res-ca/cancel")
    assert cancel_response.status_code == 200
    reservation = cancel_response.get_json()
    assert reservation["state"] == "cancelled"

    item_response = client.get("/items/SKU-CA")
    item = item_response.get_json()
    assert item["reserved_qty"] == 0
    assert item["available_qty"] == 8


def test_sweep_expires_stale(client):
    _create_item(client, sku="SKU-SW", qty=12)
    response = _create_reservation(client, reservation_key="res-sw", sku="SKU-SW", quantity=4)
    assert response.status_code == 201

    with client.application.app_context():
        db.session.execute(
            update(StockReservation)
            .where(StockReservation.reservation_key == "res-sw")
            .values(expires_at=datetime.utcnow() - timedelta(seconds=5))
        )
        db.session.commit()

    sweep_response = client.post("/sweeps/expire")
    assert sweep_response.status_code == 200
    result = sweep_response.get_json()
    assert result["expired_count"] == 1
    assert result["failed_count"] == 0

    reservation_response = client.get("/reservations/res-sw")
    reservation = reservation_response.get_json()
    assert reservation["state"] == "expired"

    item_response = client.get("/items/SKU-SW")
    item = item_response.get_json()
    assert item["reserved_qty"] == 0
    assert item["available_qty"] == 12


def test_sweep_savepoint_isolation(client):
    _create_item(client, sku="SKU-GOOD", qty=10)
    _create_item(client, sku="SKU-BAD", qty=10)

    good_response = _create_reservation(
        client, reservation_key="res-good", sku="SKU-GOOD", quantity=2
    )
    bad_response = _create_reservation(client, reservation_key="res-bad", sku="SKU-BAD", quantity=2)
    assert good_response.status_code == 201
    assert bad_response.status_code == 201

    with client.application.app_context():
        db.session.execute(
            update(StockReservation)
            .where(StockReservation.reservation_key.in_(["res-good", "res-bad"]))
            .values(expires_at=datetime.utcnow() - timedelta(seconds=5))
        )
        bad_item = db.session.execute(
            select(InventoryItem).where(InventoryItem.sku == "SKU-BAD")
        ).scalar_one()
        db.session.execute(
            update(InventoryItem).where(InventoryItem.id == bad_item.id).values(reserved_qty=0)
        )
        db.session.commit()

    sweep_response = client.post("/sweeps/expire")
    assert sweep_response.status_code == 200
    result = sweep_response.get_json()
    assert result["expired_count"] == 1
    assert result["failed_count"] == 1

    good_res = client.get("/reservations/res-good").get_json()
    bad_res = client.get("/reservations/res-bad").get_json()
    assert good_res["state"] == "expired"
    assert bad_res["state"] == "active"


def test_concurrent_reserve_no_oversubscribe(client):
    _create_item(client, sku="SKU-RACE", qty=5)
    first = _create_reservation(client, reservation_key="res-r1", sku="SKU-RACE", quantity=3)
    second = _create_reservation(client, reservation_key="res-r2", sku="SKU-RACE", quantity=3)

    assert first.status_code == 201
    assert second.status_code in (409, 422)

    item = client.get("/items/SKU-RACE").get_json()
    assert item["reserved_qty"] == 3
    assert item["available_qty"] == 2
