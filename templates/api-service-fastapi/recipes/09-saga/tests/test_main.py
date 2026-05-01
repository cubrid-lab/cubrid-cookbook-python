import sys
from pathlib import Path
from importlib import import_module

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

Base = import_module("database").Base
get_db = import_module("database").get_db
app = import_module("main").app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.state.testing_session_local = TestingSessionLocal
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    del app.state.testing_session_local
    app.dependency_overrides.clear()


def _seed(client: TestClient, qty: int = 10, cents: int = 5000):
    client.post("/inventory-items", json={"sku": "SKU-1", "available_qty": qty})
    client.post("/payment-accounts", json={"client_id": "C1", "available_cents": cents})


def _create_order(client: TestClient, order_key: str = "O-1", qty: int = 3, total: int = 1200):
    return client.post(
        "/orders",
        json={
            "order_key": order_key,
            "client_id": "C1",
            "sku": "SKU-1",
            "quantity": qty,
            "total_cents": total,
        },
    )


def test_full_saga_success(client: TestClient):
    _seed(client)
    create_resp = _create_order(client)
    assert create_resp.status_code == 201

    exec_resp = client.post("/orders/O-1/execute")
    assert exec_resp.status_code == 200
    assert exec_resp.json()["state"] == "completed"


def test_payment_failure_compensates_inventory(client: TestClient):
    _seed(client, qty=10, cents=500)
    _create_order(client, total=1200)

    exec_resp = client.post("/orders/O-1/execute")
    assert exec_resp.status_code == 422

    order = client.get("/orders/O-1").json()
    assert order["state"] == "compensated"

    steps = client.get("/orders/O-1/steps").json()
    reserve = next(step for step in steps if step["step_name"] == "reserve_inventory")
    assert reserve["status"] == "compensated"


def test_inventory_failure_no_compensation_needed(client: TestClient):
    _seed(client, qty=1, cents=5000)
    _create_order(client, qty=3)

    exec_resp = client.post("/orders/O-1/execute")
    assert exec_resp.status_code == 422

    order = client.get("/orders/O-1").json()
    assert order["state"] == "compensated"

    steps = client.get("/orders/O-1/steps").json()
    reserve = next(step for step in steps if step["step_name"] == "reserve_inventory")
    assert reserve["status"] == "failed"
    assert reserve["compensation_attempt_count"] == 0


def test_concurrent_execute_conflict(client: TestClient):
    _seed(client)
    _create_order(client)

    from sqlalchemy import update

    SessionLocal = app.state.testing_session_local
    Order = import_module("models").Order

    db = SessionLocal()
    try:
        db.execute(
            update(Order)
            .where(Order.order_key == "O-1")
            .values(state="processing", version=Order.version + 1)
        )
        db.commit()
    finally:
        db.close()

    conflict = client.post("/orders/O-1/execute")
    assert conflict.status_code == 409


def test_idempotent_after_completion(client: TestClient):
    _seed(client)
    _create_order(client)

    first = client.post("/orders/O-1/execute")
    second = client.post("/orders/O-1/execute")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["state"] == "completed"


def test_step_log_shows_statuses(client: TestClient):
    _seed(client, qty=10, cents=100)
    _create_order(client, total=1200)
    client.post("/orders/O-1/execute")

    steps = client.get("/orders/O-1/steps")
    assert steps.status_code == 200
    payload = {step["step_name"]: step for step in steps.json()}
    assert payload["reserve_inventory"]["status"] == "compensated"
    assert payload["charge_payment"]["status"] == "failed"
    assert payload["confirm_shipment"]["status"] == "pending"


def test_duplicate_order_key_409(client: TestClient):
    _seed(client)
    first = _create_order(client, order_key="O-dup")
    second = _create_order(client, order_key="O-dup")

    assert first.status_code == 201
    assert second.status_code == 409
