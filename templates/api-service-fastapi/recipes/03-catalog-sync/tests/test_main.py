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


from typing import cast



def build_items(price_offset: int = 0) -> list[dict[str, object]]:
    return [
        {
            "external_sku": "SKU-001",
            "name": "Widget A",
            "price": 1000 + price_offset,
            "available": 1,
        },
        {
            "external_sku": "SKU-002",
            "name": "Widget B",
            "price": 2000 + price_offset,
            "available": 1,
        },
        {
            "external_sku": "SKU-003",
            "name": "Widget C",
            "price": 3000 + price_offset,
            "available": 0,
        },
    ]


@pytest.mark.asyncio
async def test_sync_creates_new_items(client: AsyncClient) -> None:
    payload = {"source": "erp", "items": build_items()}
    response = await client.post("/catalog/sync", json=payload)

    assert response.status_code == 200
    body = cast(dict[str, object], response.json())
    assert body["status"] == "completed"
    assert body["total_rows"] == 3
    assert body["created_cnt"] == 3
    assert body["updated_cnt"] == 0
    assert body["failed_cnt"] == 0


@pytest.mark.asyncio
async def test_sync_updates_existing_items(client: AsyncClient) -> None:
    _ = await client.post("/catalog/sync", json={"source": "erp", "items": build_items()})

    response = await client.post(
        "/catalog/sync",
        json={"source": "erp", "items": build_items(price_offset=500)},
    )

    assert response.status_code == 200
    body = cast(dict[str, object], response.json())
    assert body["created_cnt"] == 0
    assert body["updated_cnt"] == 3

    items_response = await client.get("/catalog/items")
    items = cast(list[dict[str, object]], items_response.json())
    assert len(items) == 3
    for item in items:
        assert item["source_version"] == 2


@pytest.mark.asyncio
async def test_sync_idempotent(client: AsyncClient) -> None:
    payload = {"source": "erp", "items": build_items()}

    first = await client.post("/catalog/sync", json=payload)
    second = await client.post("/catalog/sync", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    second_body = cast(dict[str, object], second.json())
    assert second_body["created_cnt"] == 0
    assert second_body["updated_cnt"] == 3

    items_response = await client.get("/catalog/items")
    items = cast(list[dict[str, object]], items_response.json())
    assert len(items) == 3


@pytest.mark.asyncio
async def test_sync_mixed_create_and_update(client: AsyncClient) -> None:
    initial = {
        "source": "erp",
        "items": [{"external_sku": "SKU-001", "name": "Widget A", "price": 1000, "available": 1}],
    }
    _ = await client.post("/catalog/sync", json=initial)

    mixed_payload = {
        "source": "erp",
        "items": [
            {"external_sku": "SKU-001", "name": "Widget A+", "price": 1100, "available": 1},
            {"external_sku": "SKU-004", "name": "Widget D", "price": 4000, "available": 1},
            {"external_sku": "SKU-005", "name": "Widget E", "price": 5000, "available": 0},
        ],
    }
    response = await client.post("/catalog/sync", json=mixed_payload)

    assert response.status_code == 200
    body = cast(dict[str, object], response.json())
    assert body["created_cnt"] == 2
    assert body["updated_cnt"] == 1


@pytest.mark.asyncio
async def test_list_catalog_items(client: AsyncClient) -> None:
    _ = await client.post("/catalog/sync", json={"source": "erp", "items": build_items()})

    response = await client.get("/catalog/items", params={"skip": 1, "limit": 2})
    assert response.status_code == 200
    items = cast(list[dict[str, object]], response.json())
    assert len(items) == 2
    assert items[0]["external_sku"] == "SKU-002"
    assert items[1]["external_sku"] == "SKU-003"


@pytest.mark.asyncio
async def test_get_sync_run(client: AsyncClient) -> None:
    sync_response = await client.post(
        "/catalog/sync",
        json={"source": "erp", "items": build_items()},
    )
    run = cast(dict[str, object], sync_response.json())

    response = await client.get(f"/catalog/sync-runs/{run['id']}")
    assert response.status_code == 200
    body = cast(dict[str, object], response.json())
    assert body["id"] == run["id"]
    assert body["source"] == "erp"
    assert body["status"] == "completed"
    assert body["total_rows"] == 3


@pytest.mark.asyncio
async def test_sync_empty_items_rejected(client: AsyncClient) -> None:
    response = await client.post("/catalog/sync", json={"source": "erp", "items": []})
    assert response.status_code == 422
