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


import json
from typing import cast



@pytest.mark.asyncio
async def test_create_profile(client: AsyncClient) -> None:
    payload = {
        "email": "audit-create@example.com",
        "display_name": "Audit User",
        "bio": "Created profile",
    }
    response = await client.post("/profiles", json=payload)

    assert response.status_code == 201
    created = cast(dict[str, object], response.json())
    assert cast(int, created["id"]) > 0
    assert created["email"] == payload["email"]
    assert created["display_name"] == payload["display_name"]
    assert created["bio"] == payload["bio"]
    assert created["version"] == 1


@pytest.mark.asyncio
async def test_create_duplicate_email_409(client: AsyncClient) -> None:
    payload = {
        "email": "audit-dup@example.com",
        "display_name": "First",
        "bio": None,
    }
    first = await client.post("/profiles", json=payload)
    assert first.status_code == 201

    second = await client.post("/profiles", json=payload)
    assert second.status_code == 409
    assert second.json() == {"detail": "Email already exists"}


@pytest.mark.asyncio
async def test_update_profile_success(client: AsyncClient) -> None:
    created_response = await client.post(
        "/profiles",
        json={"email": "audit-update@example.com", "display_name": "Initial", "bio": "Before"},
    )
    created = cast(dict[str, object], created_response.json())

    update_response = await client.patch(
        f"/profiles/{created['id']}",
        json={"expected_version": 1, "display_name": "Updated", "bio": "After"},
    )

    assert update_response.status_code == 200
    updated = cast(dict[str, object], update_response.json())
    assert updated["id"] == created["id"]
    assert updated["email"] == created["email"]
    assert updated["display_name"] == "Updated"
    assert updated["bio"] == "After"
    assert updated["version"] == 2


@pytest.mark.asyncio
async def test_update_stale_version_409(client: AsyncClient) -> None:
    created_response = await client.post(
        "/profiles",
        json={"email": "audit-stale@example.com", "display_name": "Initial", "bio": None},
    )
    created = cast(dict[str, object], created_response.json())

    response = await client.patch(
        f"/profiles/{created['id']}",
        json={"expected_version": 999, "display_name": "Ignored"},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Stale version"}


@pytest.mark.asyncio
async def test_update_records_event(client: AsyncClient) -> None:
    created_response = await client.post(
        "/profiles",
        json={"email": "audit-event@example.com", "display_name": "Initial", "bio": None},
    )
    created = cast(dict[str, object], created_response.json())

    _ = await client.patch(
        f"/profiles/{created['id']}",
        json={"expected_version": 1, "display_name": "New Name", "bio": "Now set"},
    )

    events_response = await client.get(f"/profiles/{created['id']}/events")
    assert events_response.status_code == 200
    events = cast(list[dict[str, object]], events_response.json())
    assert len(events) == 2
    assert events[1]["event_type"] == "updated"
    payload = cast(str, events[1]["payload"])
    changed = cast(dict[str, object], json.loads(payload))
    assert changed["display_name"] == "New Name"
    assert changed["bio"] == "Now set"


@pytest.mark.asyncio
async def test_event_list_ordered_by_version(client: AsyncClient) -> None:
    created_response = await client.post(
        "/profiles",
        json={"email": "audit-ordered@example.com", "display_name": "Name", "bio": None},
    )
    created = cast(dict[str, object], created_response.json())

    _ = await client.patch(
        f"/profiles/{created['id']}",
        json={"expected_version": 1, "display_name": "Name 2"},
    )
    _ = await client.patch(
        f"/profiles/{created['id']}",
        json={"expected_version": 2, "display_name": "Name 3"},
    )

    events_response = await client.get(f"/profiles/{created['id']}/events")
    assert events_response.status_code == 200
    events = cast(list[dict[str, object]], events_response.json())
    assert [event["version"] for event in events] == [1, 2, 3]


@pytest.mark.asyncio
async def test_get_single_event(client: AsyncClient) -> None:
    created_response = await client.post(
        "/profiles",
        json={"email": "audit-single@example.com", "display_name": "Single", "bio": None},
    )
    created = cast(dict[str, object], created_response.json())

    _ = await client.patch(
        f"/profiles/{created['id']}",
        json={"expected_version": 1, "display_name": "Single Updated"},
    )

    response = await client.get(f"/profiles/{created['id']}/events/2")
    assert response.status_code == 200
    event = cast(dict[str, object], response.json())
    assert event["profile_id"] == created["id"]
    assert event["version"] == 2
    assert event["event_type"] == "updated"
