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
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_task_crud_flow(client: AsyncClient) -> None:
    create_payload = {
        "title": "Write cookbook tests",
        "description": "Verify CRUD endpoints",
        "completed": False,
        "priority": 2,
    }
    create_response = await client.post("/tasks", json=create_payload)

    assert create_response.status_code == 201
    created = cast(dict[str, object], create_response.json())
    assert cast(int, created["id"]) > 0
    assert created["title"] == create_payload["title"]
    assert created["description"] == create_payload["description"]
    assert created["completed"] is False
    assert created["priority"] == 2
    assert "created_at" in created
    assert "updated_at" in created

    task_id = cast(int, created["id"])

    get_response = await client.get(f"/tasks/{task_id}")
    assert get_response.status_code == 200
    fetched = cast(dict[str, object], get_response.json())
    assert fetched == created

    update_payload = {
        "title": "Write cookbook tests and docs",
        "completed": True,
        "priority": 1,
    }
    update_response = await client.put(f"/tasks/{task_id}", json=update_payload)

    assert update_response.status_code == 200
    updated = cast(dict[str, object], update_response.json())
    assert updated["id"] == task_id
    assert updated["title"] == update_payload["title"]
    assert updated["description"] == create_payload["description"]
    assert updated["completed"] is True
    assert updated["priority"] == 1

    list_response = await client.get("/tasks")
    assert list_response.status_code == 200
    listed = cast(dict[str, object], list_response.json())
    assert listed["total"] == 1
    assert listed["skip"] == 0
    assert listed["limit"] == 20
    listed_items = cast(list[dict[str, object]], listed["items"])
    assert len(listed_items) == 1
    assert listed_items[0]["id"] == task_id

    filtered_response = await client.get("/tasks", params={"completed": True, "priority": 1})
    assert filtered_response.status_code == 200
    filtered = cast(dict[str, object], filtered_response.json())
    assert filtered["total"] == 1
    filtered_items = cast(list[dict[str, object]], filtered["items"])
    assert len(filtered_items) == 1
    assert filtered_items[0]["id"] == task_id

    delete_response = await client.delete(f"/tasks/{task_id}")
    assert delete_response.status_code == 204
    assert delete_response.text == ""

    get_deleted_response = await client.get(f"/tasks/{task_id}")
    assert get_deleted_response.status_code == 404
    assert get_deleted_response.json() == {"detail": "Task not found"}


@pytest.mark.asyncio
async def test_not_found_update_and_delete(client: AsyncClient) -> None:
    update_response = await client.put("/tasks/9999", json={"title": "missing"})
    assert update_response.status_code == 404
    assert update_response.json() == {"detail": "Task not found"}

    delete_response = await client.delete("/tasks/9999")
    assert delete_response.status_code == 404
    assert delete_response.json() == {"detail": "Task not found"}


@pytest.mark.asyncio
async def test_validation_errors(client: AsyncClient) -> None:
    invalid_create = await client.post(
        "/tasks",
        json={"title": "", "priority": 9},
    )
    assert invalid_create.status_code == 422
    body = cast(dict[str, object], invalid_create.json())
    assert body["message"] == "Validation failed"
    assert isinstance(body["detail"], list)

    invalid_list = await client.get("/tasks", params={"skip": -1})
    assert invalid_list.status_code == 422
    invalid_list_body = cast(dict[str, object], invalid_list.json())
    assert invalid_list_body["message"] == "Validation failed"
    assert isinstance(invalid_list_body["detail"], list)
