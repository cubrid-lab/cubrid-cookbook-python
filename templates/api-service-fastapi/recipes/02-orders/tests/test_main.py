# pyright: reportImplicitRelativeImport=false, reportAny=false
from typing import cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    session = session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest_asyncio.fixture()
async def client(db_session: Session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_customer_crud(client: AsyncClient) -> None:
    payload = {"name": "Alice", "email": "alice@example.com"}
    create_response = await client.post("/customers", json=payload)
    assert create_response.status_code == 201
    created = cast(dict[str, object], create_response.json())
    assert cast(int, created["id"]) > 0
    assert created["name"] == payload["name"]
    assert created["email"] == payload["email"]
    assert "created_at" in created
    customer_id = cast(int, created["id"])
    get_response = await client.get(f"/customers/{customer_id}")
    assert get_response.status_code == 200
    fetched = cast(dict[str, object], get_response.json())
    assert fetched == created


@pytest.mark.asyncio
async def test_product_crud(client: AsyncClient) -> None:
    payload = {"name": "Keyboard", "price": 12345, "stock": 10}
    create_response = await client.post("/products", json=payload)
    assert create_response.status_code == 201
    created = cast(dict[str, object], create_response.json())
    assert cast(int, created["id"]) > 0
    assert created["name"] == payload["name"]
    assert created["price"] == payload["price"]
    assert created["stock"] == payload["stock"]
    assert created["version"] == 1
    product_id = cast(int, created["id"])
    get_response = await client.get(f"/products/{product_id}")
    assert get_response.status_code == 200
    fetched = cast(dict[str, object], get_response.json())
    assert fetched == created


@pytest.mark.asyncio
async def test_order_checkout_success(client: AsyncClient) -> None:
    customer_response = await client.post(
        "/customers", json={"name": "Bob", "email": "bob@example.com"}
    )
    product_response = await client.post(
        "/products", json={"name": "Mouse", "price": 2500, "stock": 5}
    )
    customer = cast(dict[str, object], customer_response.json())
    product = cast(dict[str, object], product_response.json())
    order_response = await client.post(
        "/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 2}],
        },
    )
    assert order_response.status_code == 201
    order = cast(dict[str, object], order_response.json())
    assert order["customer_id"] == customer["id"]
    assert order["status"] == "confirmed"
    assert order["total"] == 5000
    items = cast(list[dict[str, object]], order["items"])
    assert len(items) == 1
    assert items[0]["product_id"] == product["id"]
    assert items[0]["quantity"] == 2
    assert items[0]["unit_price"] == 2500
    product_get = await client.get(f"/products/{product['id']}")
    updated_product = cast(dict[str, object], product_get.json())
    assert updated_product["stock"] == 3
    assert updated_product["version"] == 2


@pytest.mark.asyncio
async def test_order_insufficient_stock(client: AsyncClient) -> None:
    customer_response = await client.post(
        "/customers", json={"name": "Carol", "email": "carol@example.com"}
    )
    product_response = await client.post(
        "/products", json={"name": "Monitor", "price": 50000, "stock": 1}
    )
    customer = cast(dict[str, object], customer_response.json())
    product = cast(dict[str, object], product_response.json())
    order_response = await client.post(
        "/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 2}],
        },
    )
    assert order_response.status_code == 409
    assert order_response.json() == {"detail": "Insufficient stock"}


@pytest.mark.asyncio
async def test_order_cancel_restores_stock(client: AsyncClient) -> None:
    customer_response = await client.post(
        "/customers", json={"name": "Dave", "email": "dave@example.com"}
    )
    product_response = await client.post(
        "/products", json={"name": "Desk", "price": 30000, "stock": 4}
    )
    customer = cast(dict[str, object], customer_response.json())
    product = cast(dict[str, object], product_response.json())
    order_response = await client.post(
        "/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 3}],
        },
    )
    order = cast(dict[str, object], order_response.json())
    cancel_response = await client.post(f"/orders/{order['id']}/cancel")
    assert cancel_response.status_code == 200
    cancelled = cast(dict[str, object], cancel_response.json())
    assert cancelled["status"] == "cancelled"
    product_get = await client.get(f"/products/{product['id']}")
    restored_product = cast(dict[str, object], product_get.json())
    assert restored_product["stock"] == 4


@pytest.mark.asyncio
async def test_order_nonexistent_customer(client: AsyncClient) -> None:
    product_response = await client.post(
        "/products", json={"name": "Lamp", "price": 9000, "stock": 5}
    )
    product = cast(dict[str, object], product_response.json())
    order_response = await client.post(
        "/orders",
        json={"customer_id": 9999, "items": [{"product_id": product["id"], "quantity": 1}]},
    )
    assert order_response.status_code == 404
    assert order_response.json() == {"detail": "Customer not found"}


@pytest.mark.asyncio
async def test_order_nonexistent_product(client: AsyncClient) -> None:
    customer_response = await client.post(
        "/customers", json={"name": "Eve", "email": "eve@example.com"}
    )
    customer = cast(dict[str, object], customer_response.json())
    order_response = await client.post(
        "/orders",
        json={"customer_id": customer["id"], "items": [{"product_id": 9999, "quantity": 1}]},
    )
    assert order_response.status_code == 404
    assert order_response.json() == {"detail": "Product not found"}


@pytest.mark.asyncio
async def test_duplicate_customer_email_returns_409(client: AsyncClient) -> None:
    payload = {"name": "Bob", "email": "dup@example.com"}
    resp1 = await client.post("/customers", json=payload)
    assert resp1.status_code == 201
    resp2 = await client.post("/customers", json=payload)
    assert resp2.status_code == 409
    assert "email" in resp2.json()["detail"].lower()
