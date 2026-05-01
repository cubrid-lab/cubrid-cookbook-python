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



@pytest.mark.asyncio
async def test_create_document_with_first_revision(client: AsyncClient) -> None:
    response = await client.post(
        "/documents",
        json={
            "slug": "doc-one",
            "title": "Doc One",
            "body": "Initial body",
            "created_by": "alice",
        },
    )

    assert response.status_code == 201
    body = cast(dict[str, object], response.json())
    assert cast(int, body["id"]) > 0
    assert body["slug"] == "doc-one"
    assert body["title"] == "Doc One"
    assert body["version"] == 1
    assert cast(int, body["current_draft_revision_id"]) > 0
    assert body["published_revision_id"] is None


@pytest.mark.asyncio
async def test_add_new_draft_revision_increments_revision_no(client: AsyncClient) -> None:
    create_response = await client.post(
        "/documents",
        json={
            "slug": "doc-draft",
            "title": "Draft Title",
            "body": "Draft v1",
            "created_by": "alice",
        },
    )
    created = cast(dict[str, object], create_response.json())

    draft_response = await client.post(
        f"/documents/{created['id']}/drafts",
        params={"expected_version": 1},
        json={"title": "Draft Title v2", "body": "Draft v2", "created_by": "bob"},
    )

    assert draft_response.status_code == 201
    revision = cast(dict[str, object], draft_response.json())
    assert revision["document_id"] == created["id"]
    assert revision["revision_no"] == 2
    assert revision["title"] == "Draft Title v2"
    assert revision["created_by"] == "bob"


@pytest.mark.asyncio
async def test_publish_sets_published_revision_id(client: AsyncClient) -> None:
    create_response = await client.post(
        "/documents",
        json={
            "slug": "doc-publish",
            "title": "Publish Title",
            "body": "Publish v1",
            "created_by": "alice",
        },
    )
    created = cast(dict[str, object], create_response.json())

    publish_response = await client.post(
        f"/documents/{created['id']}/publish",
        params={"expected_version": 1},
    )
    assert publish_response.status_code == 200
    published = cast(dict[str, object], publish_response.json())
    assert published["published_revision_id"] == created["current_draft_revision_id"]


@pytest.mark.asyncio
async def test_restore_old_revision_creates_new_revision_with_source(client: AsyncClient) -> None:
    create_response = await client.post(
        "/documents",
        json={
            "slug": "doc-restore",
            "title": "Restore Title",
            "body": "Restore v1",
            "created_by": "alice",
        },
    )
    created = cast(dict[str, object], create_response.json())
    document_id = cast(int, created["id"])

    _ = await client.post(
        f"/documents/{document_id}/drafts",
        params={"expected_version": 1},
        json={"title": "Restore Title v2", "body": "Restore v2", "created_by": "bob"},
    )

    restore_response = await client.post(
        f"/documents/{document_id}/restore/1",
        params={"expected_version": 2, "created_by": "charlie"},
    )
    assert restore_response.status_code == 200
    restored = cast(dict[str, object], restore_response.json())
    assert restored["revision_no"] == 3
    assert restored["source_revision_id"] == 1
    assert restored["title"] == "Restore Title"
    assert restored["body"] == "Restore v1"


@pytest.mark.asyncio
async def test_optimistic_lock_conflict_on_concurrent_publish(client: AsyncClient) -> None:
    create_response = await client.post(
        "/documents",
        json={
            "slug": "doc-stale-publish",
            "title": "Stale Publish",
            "body": "Stale body",
            "created_by": "alice",
        },
    )
    created = cast(dict[str, object], create_response.json())
    document_id = cast(int, created["id"])

    first_publish = await client.post(
        f"/documents/{document_id}/publish",
        params={"expected_version": 1},
    )
    assert first_publish.status_code == 200

    second_publish = await client.post(
        f"/documents/{document_id}/publish",
        params={"expected_version": 1},
    )
    assert second_publish.status_code == 409
    assert second_publish.json() == {"detail": "Stale version"}


@pytest.mark.asyncio
async def test_slug_lookup_works(client: AsyncClient) -> None:
    _ = await client.post(
        "/documents",
        json={
            "slug": "doc-by-slug",
            "title": "Lookup Title",
            "body": "Lookup body",
            "created_by": "alice",
        },
    )

    response = await client.get("/documents/by-slug/doc-by-slug")
    assert response.status_code == 200
    body = cast(dict[str, object], response.json())
    assert body["slug"] == "doc-by-slug"
    assert body["title"] == "Lookup Title"
