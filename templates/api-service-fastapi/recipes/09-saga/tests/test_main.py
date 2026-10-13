import sys
from pathlib import Path
from importlib import import_module

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

get_db = import_module("database").get_db
app = import_module("main").app


@pytest.fixture
def client(engine: Engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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


def _force_processing(order_key: str, age_seconds: int) -> None:
    from datetime import timedelta

    from sqlalchemy import update

    models = import_module("models")
    db = app.state.testing_session_local()
    try:
        db.execute(
            update(models.Order)
            .where(models.Order.order_key == order_key)
            .values(
                state="processing",
                updated_at=models.naive_utc_now() - timedelta(seconds=age_seconds),
            )
        )
        db.commit()
    finally:
        db.close()


def test_recover_recently_started_order_conflicts(client: TestClient):
    _seed(client)
    _create_order(client)
    _force_processing("O-1", age_seconds=1)

    response = client.post("/orders/O-1/recover", json={"timeout_seconds": 300})

    assert response.status_code == 409
    assert "timeout is 300s" in response.json()["detail"]


def test_recover_stuck_order_resets_to_pending(client: TestClient):
    _seed(client)
    _create_order(client)
    _force_processing("O-1", age_seconds=600)

    response = client.post("/orders/O-1/recover", json={"timeout_seconds": 300})

    assert response.status_code == 200
    assert response.json()["state"] == "pending"


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


def _crash_after(order_key: str, steps: list[str]) -> None:
    """Leave the database as an execute run that crashed after ``steps`` committed.

    Each step's effect and its ``done`` status commit together, then the process
    dies with the order still ``processing``. The order is aged past the recover
    timeout.
    """
    from datetime import timedelta

    from sqlalchemy import and_, update

    models = import_module("models")
    db = app.state.testing_session_local()
    try:
        order = db.query(models.Order).filter(models.Order.order_key == order_key).one()
        for step_name in steps:
            if step_name == "reserve_inventory":
                db.execute(
                    update(models.InventoryItem)
                    .where(models.InventoryItem.sku == order.sku)
                    .values(
                        reserved_qty=models.InventoryItem.reserved_qty + order.quantity,
                        available_qty=models.InventoryItem.available_qty - order.quantity,
                    )
                )
            if step_name == "charge_payment":
                db.execute(
                    update(models.PaymentAccount)
                    .where(models.PaymentAccount.client_id == order.client_id)
                    .values(
                        held_cents=models.PaymentAccount.held_cents + order.total_cents,
                        available_cents=models.PaymentAccount.available_cents - order.total_cents,
                    )
                )
            db.execute(
                update(models.SagaStep)
                .where(
                    and_(
                        models.SagaStep.order_id == order.id,
                        models.SagaStep.step_name == step_name,
                    )
                )
                .values(status="done", attempt_count=1, executed_at=models.naive_utc_now())
            )
        db.execute(
            update(models.Order)
            .where(models.Order.id == order.id)
            .values(
                state="processing",
                version=models.Order.version + 1,
                updated_at=models.naive_utc_now() - timedelta(seconds=600),
            )
        )
        db.commit()
    finally:
        db.close()


def _balances() -> tuple[int, int, int, int]:
    models = import_module("models")
    db = app.state.testing_session_local()
    try:
        item = db.query(models.InventoryItem).filter(models.InventoryItem.sku == "SKU-1").one()
        account = (
            db.query(models.PaymentAccount).filter(models.PaymentAccount.client_id == "C1").one()
        )
        return item.available_qty, item.reserved_qty, account.available_cents, account.held_cents
    finally:
        db.close()


@pytest.mark.parametrize(
    "committed",
    [["reserve_inventory"], ["reserve_inventory", "charge_payment"]],
    ids=["after-reserve", "after-charge"],
)
def test_recover_then_execute_applies_each_step_once(client: TestClient, committed: list[str]):
    _seed(client, qty=10, cents=5000)
    _create_order(client, qty=3, total=1200)
    _crash_after("O-1", committed)

    assert client.post("/orders/O-1/recover", json={"timeout_seconds": 300}).json()["state"] == (
        "pending"
    )
    response = client.post("/orders/O-1/execute")

    assert response.status_code == 200
    assert response.json()["state"] == "completed"
    # Stock reserved and payment held exactly once: 3 units and 1200 cents.
    assert _balances() == (7, 3, 3800, 1200)
    steps = {step["step_name"]: step for step in client.get("/orders/O-1/steps").json()}
    assert {name: step["status"] for name, step in steps.items()} == {
        "reserve_inventory": "done",
        "charge_payment": "done",
        "confirm_shipment": "done",
    }
    for name in committed:
        assert steps[name]["attempt_count"] == 1


def test_resumed_run_compensates_the_step_it_skipped(client: TestClient):
    _seed(client, qty=10, cents=500)
    _create_order(client, qty=3, total=1200)
    _crash_after("O-1", ["reserve_inventory"])

    client.post("/orders/O-1/recover", json={"timeout_seconds": 300})
    response = client.post("/orders/O-1/execute")

    assert response.status_code == 422
    # The payment fails, so the reservation made before the crash is released.
    assert _balances() == (10, 0, 500, 0)
    steps = {step["step_name"]: step["status"] for step in client.get("/orders/O-1/steps").json()}
    assert steps["reserve_inventory"] == "compensated"
    assert steps["charge_payment"] == "failed"
