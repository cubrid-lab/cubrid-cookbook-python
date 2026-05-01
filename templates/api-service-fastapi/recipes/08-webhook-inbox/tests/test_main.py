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


from models import Shipment

from typing import cast




@pytest.mark.asyncio
async def test_ingest_webhook_creates_event(client: AsyncClient) -> None:
    shipment_response = await client.post(
        "/webhooks/shipments",
        json={"external_ref": "ship-create-1", "carrier": "ups"},
    )
    assert shipment_response.status_code == 201

    response = await client.post(
        "/webhooks/ingest",
        json={
            "provider": "carrier-x",
            "external_event_id": "evt-create-1",
            "event_type": "in_transit",
            "payload": '{"status":"in_transit"}',
            "shipment_external_ref": "ship-create-1",
        },
    )

    assert response.status_code == 201
    body = cast(dict[str, object], response.json())
    assert cast(int, body["id"]) > 0
    assert body["provider"] == "carrier-x"
    assert body["external_event_id"] == "evt-create-1"
    assert body["status"] == "received"


@pytest.mark.asyncio
async def test_duplicate_ingest_is_idempotent(client: AsyncClient) -> None:
    payload = {
        "provider": "carrier-y",
        "external_event_id": "evt-idem-1",
        "event_type": "in_transit",
        "payload": '{"status":"in_transit"}',
        "shipment_external_ref": None,
    }

    first = await client.post("/webhooks/ingest", json=payload)
    second = await client.post("/webhooks/ingest", json=payload)

    assert first.status_code == 201
    assert second.status_code == 200
    first_body = cast(dict[str, object], first.json())
    second_body = cast(dict[str, object], second.json())
    assert second_body["id"] == first_body["id"]

    events_response = await client.get("/webhooks/events")
    events = cast(list[dict[str, object]], events_response.json())
    matches = [item for item in events if item["external_event_id"] == "evt-idem-1"]
    assert len(matches) == 1


@pytest.mark.asyncio
async def test_process_batch_updates_shipment_status(
    client: AsyncClient,
    db_session: Session,
) -> None:
    create_shipment = await client.post(
        "/webhooks/shipments",
        json={"external_ref": "ship-delivered-1", "carrier": "fedex"},
    )
    assert create_shipment.status_code == 201

    ingest = await client.post(
        "/webhooks/ingest",
        json={
            "provider": "carrier-z",
            "external_event_id": "evt-delivered-1",
            "event_type": "package_delivered",
            "payload": '{"status":"delivered"}',
            "shipment_external_ref": "ship-delivered-1",
        },
    )
    event = cast(dict[str, object], ingest.json())

    process = await client.post(
        "/webhooks/process",
        json={"processor_token": "proc-1", "max_events": 5},
    )
    assert process.status_code == 200
    process_body = cast(dict[str, object], process.json())
    assert process_body == {"processed": 1, "failed": 0, "dead_lettered": 0}

    event_response = await client.get(f"/webhooks/events/{event['id']}")
    processed_event = cast(dict[str, object], event_response.json())
    assert processed_event["status"] == "processed"
    assert processed_event["attempts"] == 1

    shipment_id = cast(int, processed_event["shipment_id"])
    shipment = db_session.get(Shipment, shipment_id)
    assert shipment is not None
    assert shipment.current_status == "delivered"
    assert shipment.delivered_at is not None


@pytest.mark.asyncio
async def test_failed_processing_marks_failed(client: AsyncClient) -> None:
    ingest = await client.post(
        "/webhooks/ingest",
        json={
            "provider": "carrier-a",
            "external_event_id": "evt-fail-1",
            "event_type": "label_created",
            "payload": '{"status":"label_created"}',
            "shipment_external_ref": "missing-ref",
        },
    )
    event = cast(dict[str, object], ingest.json())

    process = await client.post(
        "/webhooks/process",
        json={"processor_token": "proc-2", "max_events": 5},
    )
    assert process.status_code == 200
    assert process.json() == {"processed": 0, "failed": 1, "dead_lettered": 0}

    event_response = await client.get(f"/webhooks/events/{event['id']}")
    failed_event = cast(dict[str, object], event_response.json())
    assert failed_event["status"] == "failed"
    assert failed_event["attempts"] == 1
    assert failed_event["last_error"] == "Shipment not linked"
    attempts_list = cast(list[dict[str, object]], failed_event["attempts_list"])
    assert len(attempts_list) == 1
    assert attempts_list[0]["outcome"] == "failed"


@pytest.mark.asyncio
async def test_dead_letter_after_three_attempts(client: AsyncClient) -> None:
    ingest = await client.post(
        "/webhooks/ingest",
        json={
            "provider": "carrier-b",
            "external_event_id": "evt-dead-1",
            "event_type": "exception",
            "payload": '{"status":"exception"}',
            "shipment_external_ref": None,
        },
    )
    event = cast(dict[str, object], ingest.json())

    first = await client.post(
        "/webhooks/process", json={"processor_token": "proc-3", "max_events": 5}
    )
    retry_1 = await client.post(f"/webhooks/events/{event['id']}/retry")
    assert retry_1.status_code == 200
    second = await client.post(
        "/webhooks/process", json={"processor_token": "proc-3", "max_events": 5}
    )
    retry_2 = await client.post(f"/webhooks/events/{event['id']}/retry")
    assert retry_2.status_code == 200
    third = await client.post(
        "/webhooks/process", json={"processor_token": "proc-3", "max_events": 5}
    )

    assert first.json() == {"processed": 0, "failed": 1, "dead_lettered": 0}
    assert second.json() == {"processed": 0, "failed": 1, "dead_lettered": 0}
    assert third.json() == {"processed": 0, "failed": 0, "dead_lettered": 1}

    event_response = await client.get(f"/webhooks/events/{event['id']}")
    dead_event = cast(dict[str, object], event_response.json())
    assert dead_event["status"] == "dead_letter"
    assert dead_event["attempts"] == 3


@pytest.mark.asyncio
async def test_retry_resets_failed_event_to_received(client: AsyncClient) -> None:
    ingest = await client.post(
        "/webhooks/ingest",
        json={
            "provider": "carrier-c",
            "external_event_id": "evt-retry-1",
            "event_type": "label_created",
            "payload": '{"status":"label_created"}',
            "shipment_external_ref": None,
        },
    )
    event = cast(dict[str, object], ingest.json())

    process = await client.post(
        "/webhooks/process",
        json={"processor_token": "proc-4", "max_events": 5},
    )
    assert process.json() == {"processed": 0, "failed": 1, "dead_lettered": 0}

    retry = await client.post(f"/webhooks/events/{event['id']}/retry")
    assert retry.status_code == 200
    retried = cast(dict[str, object], retry.json())
    assert retried["status"] == "received"
    assert retried["attempts"] == 1
    assert retried["last_error"] is None
