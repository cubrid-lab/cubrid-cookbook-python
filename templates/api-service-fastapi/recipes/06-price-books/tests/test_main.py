# pyright: reportImplicitRelativeImport=false, reportAny=false
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
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
    app.dependency_overrides.clear()


from datetime import datetime
from typing import cast


BASE_PRODUCTS_PATH = "/prices"
BASE_PRICES_PATH = "/prices/prices"


def iso(dt: str) -> str:
    return datetime.fromisoformat(dt).isoformat()


async def create_price_product(client: AsyncClient, sku: str, name: str) -> dict[str, object]:
    response = await client.post(f"{BASE_PRODUCTS_PATH}/products", json={"sku": sku, "name": name})
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


async def create_price_entry(client: AsyncClient, payload: dict[str, object]) -> dict[str, object]:
    response = await client.post(BASE_PRICES_PATH, json=payload)
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


@pytest.mark.asyncio
async def test_create_open_ended_price_and_query_as_of(client: AsyncClient) -> None:
    product = await create_price_product(client, "SKU-OPEN-1", "Open Product")
    _ = await create_price_entry(
        client,
        {
            "product_id": product["id"],
            "channel": "web",
            "currency": "USD",
            "amount_cents": 1299,
            "starts_at": iso("2026-01-01T00:00:00"),
            "ends_at": None,
        },
    )

    response = await client.get(
        f"{BASE_PRODUCTS_PATH}/products/{product['id']}/price",
        params={"channel": "web", "currency": "USD", "at": iso("2026-03-01T09:00:00")},
    )
    assert response.status_code == 200
    body = cast(dict[str, object], response.json())
    assert body["product_id"] == product["id"]
    assert body["amount_cents"] == 1299
    assert body["ends_at"] is None


@pytest.mark.asyncio
async def test_reject_overlapping_entry_409(client: AsyncClient) -> None:
    product = await create_price_product(client, "SKU-OVERLAP-1", "Overlap Product")
    _ = await create_price_entry(
        client,
        {
            "product_id": product["id"],
            "channel": "web",
            "currency": "USD",
            "amount_cents": 1000,
            "starts_at": iso("2026-01-01T00:00:00"),
            "ends_at": iso("2026-02-01T00:00:00"),
        },
    )

    response = await client.post(
        BASE_PRICES_PATH,
        json={
            "product_id": product["id"],
            "channel": "web",
            "currency": "USD",
            "amount_cents": 1500,
            "starts_at": iso("2026-01-15T00:00:00"),
            "ends_at": iso("2026-03-01T00:00:00"),
        },
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Overlapping price range"}


@pytest.mark.asyncio
async def test_allow_adjacent_entries(client: AsyncClient) -> None:
    product = await create_price_product(client, "SKU-ADJ-1", "Adjacent Product")
    _ = await create_price_entry(
        client,
        {
            "product_id": product["id"],
            "channel": "web",
            "currency": "USD",
            "amount_cents": 1000,
            "starts_at": iso("2026-01-01T00:00:00"),
            "ends_at": iso("2026-02-01T00:00:00"),
        },
    )

    response = await client.post(
        BASE_PRICES_PATH,
        json={
            "product_id": product["id"],
            "channel": "web",
            "currency": "USD",
            "amount_cents": 1200,
            "starts_at": iso("2026-02-01T00:00:00"),
            "ends_at": iso("2026-03-01T00:00:00"),
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_as_of_returns_correct_price(client: AsyncClient) -> None:
    product = await create_price_product(client, "SKU-ASOF-1", "As Of Product")
    _ = await create_price_entry(
        client,
        {
            "product_id": product["id"],
            "channel": "web",
            "currency": "USD",
            "amount_cents": 2100,
            "starts_at": iso("2026-01-01T00:00:00"),
            "ends_at": iso("2026-02-01T00:00:00"),
        },
    )
    _ = await create_price_entry(
        client,
        {
            "product_id": product["id"],
            "channel": "web",
            "currency": "USD",
            "amount_cents": 2600,
            "starts_at": iso("2026-02-01T00:00:00"),
            "ends_at": None,
        },
    )

    response = await client.get(
        f"{BASE_PRODUCTS_PATH}/products/{product['id']}/price",
        params={"channel": "web", "currency": "USD", "at": iso("2026-02-10T12:00:00")},
    )
    assert response.status_code == 200
    body = cast(dict[str, object], response.json())
    assert body["amount_cents"] == 2600


@pytest.mark.asyncio
async def test_atomic_supersede_closes_old_and_creates_new(client: AsyncClient) -> None:
    product = await create_price_product(client, "SKU-SUP-1", "Supersede Product")
    original = await create_price_entry(
        client,
        {
            "product_id": product["id"],
            "channel": "web",
            "currency": "USD",
            "amount_cents": 5000,
            "starts_at": iso("2026-01-01T00:00:00"),
            "ends_at": None,
        },
    )

    response = await client.post(
        f"{BASE_PRICES_PATH}/{original['id']}/supersede",
        json={"new_amount_cents": 5500, "effective_at": iso("2026-02-01T00:00:00")},
    )
    assert response.status_code == 201
    superseded = cast(dict[str, object], response.json())
    assert superseded["amount_cents"] == 5500
    assert superseded["starts_at"] == iso("2026-02-01T00:00:00")

    list_response = await client.get(f"{BASE_PRODUCTS_PATH}/products/{product['id']}/prices")
    assert list_response.status_code == 200
    entries = cast(list[dict[str, object]], list_response.json())
    assert len(entries) == 2
    assert entries[0]["id"] == original["id"]
    assert entries[0]["ends_at"] == iso("2026-02-01T00:00:00")
    assert entries[1]["amount_cents"] == 5500
    assert entries[1]["ends_at"] is None


@pytest.mark.asyncio
async def test_different_channel_same_product_ok(client: AsyncClient) -> None:
    product = await create_price_product(client, "SKU-CHAN-1", "Channel Product")
    _ = await create_price_entry(
        client,
        {
            "product_id": product["id"],
            "channel": "web",
            "currency": "USD",
            "amount_cents": 3300,
            "starts_at": iso("2026-01-01T00:00:00"),
            "ends_at": None,
        },
    )

    response = await client.post(
        BASE_PRICES_PATH,
        json={
            "product_id": product["id"],
            "channel": "retail",
            "currency": "USD",
            "amount_cents": 3400,
            "starts_at": iso("2026-01-15T00:00:00"),
            "ends_at": None,
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_reject_inverted_range_422(client: AsyncClient) -> None:
    product = await create_price_product(client, "SKU-INV-1", "Invalid Range Product")

    response = await client.post(
        BASE_PRICES_PATH,
        json={
            "product_id": product["id"],
            "channel": "web",
            "currency": "USD",
            "amount_cents": 999,
            "starts_at": iso("2026-03-01T00:00:00"),
            "ends_at": iso("2026-03-01T00:00:00"),
        },
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "starts_at must be before ends_at"}
