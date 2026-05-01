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



async def create_tenant(client: AsyncClient, name: str, slug: str) -> dict[str, object]:
    response = await client.post("/tenants", json={"name": name, "slug": slug})
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


async def create_contact(
    client: AsyncClient,
    tenant_id: int,
    payload: dict[str, object],
) -> dict[str, object]:
    response = await client.post(f"/tenants/{tenant_id}/contacts", json=payload)
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


@pytest.mark.asyncio
async def test_create_tenant(client: AsyncClient) -> None:
    response = await client.post("/tenants", json={"name": "Acme", "slug": "acme"})

    assert response.status_code == 201
    body = cast(dict[str, object], response.json())
    assert cast(int, body["id"]) > 0
    assert body["name"] == "Acme"
    assert body["slug"] == "acme"
    assert "created_at" in body


@pytest.mark.asyncio
async def test_create_contact(client: AsyncClient) -> None:
    tenant = await create_tenant(client, "Tenant One", "tenant-one")

    response = await client.post(
        f"/tenants/{tenant['id']}/contacts",
        json={
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "city": "Seoul",
            "status": "active",
        },
    )

    assert response.status_code == 201
    body = cast(dict[str, object], response.json())
    assert cast(int, body["id"]) > 0
    assert body["tenant_id"] == tenant["id"]
    assert body["first_name"] == "Jane"
    assert body["email"] == "jane@example.com"


@pytest.mark.asyncio
async def test_duplicate_contact_email_per_tenant_409(client: AsyncClient) -> None:
    tenant = await create_tenant(client, "Tenant Dup", "tenant-dup")
    payload = {
        "first_name": "John",
        "last_name": "Smith",
        "email": "dup@example.com",
        "city": "Busan",
        "status": "active",
    }

    first = await client.post(f"/tenants/{tenant['id']}/contacts", json=payload)
    second = await client.post(f"/tenants/{tenant['id']}/contacts", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_same_email_different_tenants_ok(client: AsyncClient) -> None:
    tenant_a = await create_tenant(client, "Tenant A", "tenant-a")
    tenant_b = await create_tenant(client, "Tenant B", "tenant-b")
    payload = {
        "first_name": "Alex",
        "last_name": "Kim",
        "email": "shared@example.com",
        "city": "Seoul",
        "status": "active",
    }

    resp_a = await client.post(f"/tenants/{tenant_a['id']}/contacts", json=payload)
    resp_b = await client.post(f"/tenants/{tenant_b['id']}/contacts", json=payload)

    assert resp_a.status_code == 201
    assert resp_b.status_code == 201


@pytest.mark.asyncio
async def test_list_contacts_pagination(client: AsyncClient) -> None:
    tenant = await create_tenant(client, "Tenant Page", "tenant-page")
    tenant_id = cast(int, tenant["id"])

    for index in range(1, 6):
        _ = await create_contact(
            client,
            tenant_id,
            {
                "first_name": f"First{index}",
                "last_name": "User",
                "email": f"user{index}@example.com",
                "city": "Seoul",
                "status": "active",
            },
        )

    first_page_response = await client.get(f"/tenants/{tenant_id}/contacts", params={"limit": 2})
    assert first_page_response.status_code == 200
    first_page = cast(dict[str, object], first_page_response.json())
    first_items = cast(list[dict[str, object]], first_page["items"])
    first_cursor = cast(int, first_page["next_cursor"])
    assert len(first_items) == 2
    assert first_page["has_more"] is True
    assert first_page["next_cursor"] == first_items[-1]["id"]

    second_page_response = await client.get(
        f"/tenants/{tenant_id}/contacts",
        params={"cursor": first_cursor, "limit": 2},
    )
    assert second_page_response.status_code == 200
    second_page = cast(dict[str, object], second_page_response.json())
    second_items = cast(list[dict[str, object]], second_page["items"])
    second_cursor = cast(int, second_page["next_cursor"])
    assert len(second_items) == 2
    assert second_page["has_more"] is True

    third_page_response = await client.get(
        f"/tenants/{tenant_id}/contacts",
        params={"cursor": second_cursor, "limit": 2},
    )
    assert third_page_response.status_code == 200
    third_page = cast(dict[str, object], third_page_response.json())
    third_items = cast(list[dict[str, object]], third_page["items"])
    assert len(third_items) == 1
    assert third_page["has_more"] is False
    assert third_page["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_contacts_filter_by_status(client: AsyncClient) -> None:
    tenant = await create_tenant(client, "Tenant Status", "tenant-status")
    tenant_id = cast(int, tenant["id"])
    _ = await create_contact(
        client,
        tenant_id,
        {
            "first_name": "Active",
            "last_name": "One",
            "email": "active@example.com",
            "city": "Seoul",
            "status": "active",
        },
    )
    _ = await create_contact(
        client,
        tenant_id,
        {
            "first_name": "Inactive",
            "last_name": "One",
            "email": "inactive@example.com",
            "city": "Seoul",
            "status": "inactive",
        },
    )

    response = await client.get(f"/tenants/{tenant_id}/contacts", params={"status": "active"})
    assert response.status_code == 200
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    assert len(items) == 1
    assert items[0]["status"] == "active"


@pytest.mark.asyncio
async def test_list_contacts_search(client: AsyncClient) -> None:
    tenant = await create_tenant(client, "Tenant Search", "tenant-search")
    tenant_id = cast(int, tenant["id"])
    _ = await create_contact(
        client,
        tenant_id,
        {
            "first_name": "Mina",
            "last_name": "Park",
            "email": "mina@example.com",
            "city": "Seoul",
            "status": "active",
        },
    )
    _ = await create_contact(
        client,
        tenant_id,
        {
            "first_name": "Jin",
            "last_name": "Lee",
            "email": "jin@example.com",
            "city": "Busan",
            "status": "active",
        },
    )

    response = await client.get(f"/tenants/{tenant_id}/contacts", params={"q": "mina"})
    assert response.status_code == 200
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    assert len(items) == 1
    assert items[0]["email"] == "mina@example.com"


@pytest.mark.asyncio
async def test_cross_tenant_access_404(client: AsyncClient) -> None:
    tenant_a = await create_tenant(client, "Tenant Cross A", "tenant-cross-a")
    tenant_b = await create_tenant(client, "Tenant Cross B", "tenant-cross-b")
    contact = await create_contact(
        client,
        cast(int, tenant_a["id"]),
        {
            "first_name": "Owner",
            "last_name": "Only",
            "email": "owner@example.com",
            "city": "Seoul",
            "status": "active",
        },
    )

    response = await client.patch(
        f"/tenants/{tenant_b['id']}/contacts/{contact['id']}",
        json={"city": "Busan"},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Contact not found"}


@pytest.mark.asyncio
async def test_update_contact(client: AsyncClient) -> None:
    tenant = await create_tenant(client, "Tenant Update", "tenant-update")
    tenant_id = cast(int, tenant["id"])
    contact = await create_contact(
        client,
        tenant_id,
        {
            "first_name": "Before",
            "last_name": "Name",
            "email": "before@example.com",
            "city": "Seoul",
            "status": "active",
        },
    )

    response = await client.patch(
        f"/tenants/{tenant_id}/contacts/{contact['id']}",
        json={"first_name": "After", "status": "inactive", "city": "Busan"},
    )
    assert response.status_code == 200
    body = cast(dict[str, object], response.json())
    assert body["first_name"] == "After"
    assert body["status"] == "inactive"
    assert body["city"] == "Busan"


@pytest.mark.asyncio
async def test_delete_contact(client: AsyncClient) -> None:
    tenant = await create_tenant(client, "Tenant Delete", "tenant-delete")
    tenant_id = cast(int, tenant["id"])
    contact = await create_contact(
        client,
        tenant_id,
        {
            "first_name": "To",
            "last_name": "Delete",
            "email": "delete@example.com",
            "city": "Seoul",
            "status": "active",
        },
    )

    delete_response = await client.delete(f"/tenants/{tenant_id}/contacts/{contact['id']}")
    assert delete_response.status_code == 204

    list_response = await client.get(f"/tenants/{tenant_id}/contacts")
    assert list_response.status_code == 200
    body = cast(dict[str, object], list_response.json())
    items = cast(list[dict[str, object]], body["items"])
    assert items == []
