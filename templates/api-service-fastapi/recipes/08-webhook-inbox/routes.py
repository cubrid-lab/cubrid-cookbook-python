# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models import Shipment, WebhookAttempt, WebhookEvent, utc_now
from schemas import (
    ProcessRequest,
    ProcessResult,
    ShipmentCreate,
    ShipmentResponse,
    WebhookAttemptResponse,
    WebhookEventResponse,
    WebhookIngest,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def to_webhook_event_response(event: WebhookEvent) -> WebhookEventResponse:
    attempts = sorted(event.attempts_list, key=lambda item: item.attempt_no)
    return WebhookEventResponse(
        id=event.id,
        provider=event.provider,
        external_event_id=event.external_event_id,
        shipment_id=event.shipment_id,
        event_type=event.event_type,
        payload=event.payload,
        status=event.status,
        attempts=event.attempts,
        processor_token=event.processor_token,
        last_error=event.last_error,
        received_at=event.received_at,
        processed_at=event.processed_at,
        attempts_list=[WebhookAttemptResponse.model_validate(item) for item in attempts],
    )


@router.post("/shipments", response_model=ShipmentResponse, status_code=status.HTTP_201_CREATED)
def create_shipment(
    payload: ShipmentCreate,
    db: Annotated[Session, Depends(get_db)],
) -> ShipmentResponse:
    shipment = Shipment(external_ref=payload.external_ref, carrier=payload.carrier)
    db.add(shipment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shipment external_ref already exists",
        )
    db.refresh(shipment)
    return ShipmentResponse.model_validate(shipment)


@router.post("/ingest", response_model=WebhookEventResponse)
def ingest_webhook(
    payload: WebhookIngest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> WebhookEventResponse:
    shipment_id: int | None = None
    if payload.shipment_external_ref is not None:
        shipment = db.scalar(
            select(Shipment).where(Shipment.external_ref == payload.shipment_external_ref)
        )
        if shipment is not None:
            shipment_id = shipment.id

    event = WebhookEvent(
        provider=payload.provider,
        external_event_id=payload.external_event_id,
        shipment_id=shipment_id,
        shipment_external_ref=payload.shipment_external_ref,
        event_type=payload.event_type,
        payload=payload.payload,
        status="received",
        attempts=0,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_stmt = (
            select(WebhookEvent)
            .options(selectinload(WebhookEvent.attempts_list))
            .where(
                WebhookEvent.provider == payload.provider,
                WebhookEvent.external_event_id == payload.external_event_id,
            )
        )
        existing_event = db.scalar(existing_stmt)
        if existing_event is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Webhook event conflict",
            )
        response.status_code = status.HTTP_200_OK
        return to_webhook_event_response(existing_event)
    db.refresh(event)
    response.status_code = status.HTTP_201_CREATED
    return to_webhook_event_response(event)


@router.get("/events", response_model=list[WebhookEventResponse])
def list_events(
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[WebhookEventResponse]:
    stmt = (
        select(WebhookEvent)
        .options(selectinload(WebhookEvent.attempts_list))
        .order_by(WebhookEvent.id.asc())
    )
    if status_filter is not None:
        stmt = stmt.where(WebhookEvent.status == status_filter)
    events = db.scalars(stmt).all()
    return [to_webhook_event_response(event) for event in events]


@router.get("/events/{event_id}", response_model=WebhookEventResponse)
def get_event(
    event_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> WebhookEventResponse:
    stmt = (
        select(WebhookEvent)
        .options(selectinload(WebhookEvent.attempts_list))
        .where(WebhookEvent.id == event_id)
    )
    event = db.scalar(stmt)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook event not found")
    return to_webhook_event_response(event)


@router.post("/process", response_model=ProcessResult)
def process_events(
    payload: ProcessRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ProcessResult:
    stmt = (
        select(WebhookEvent)
        .where(WebhookEvent.status == "received", WebhookEvent.attempts < 3)
        .order_by(WebhookEvent.id.asc())
        .limit(payload.max_events)
    )
    events = db.scalars(stmt).all()

    processed = 0
    failed = 0
    dead_lettered = 0
    for event in events:
        claim_result = db.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == event.id, WebhookEvent.status == "received")
            .values(status="processing")
        )
        if cast(CursorResult[object], claim_result).rowcount == 0:
            continue

        db.refresh(event)
        event.attempts += 1
        event.processor_token = payload.processor_token
        attempt = WebhookAttempt(
            webhook_event_id=event.id,
            attempt_no=event.attempts,
            outcome="processed",
        )

        if event.shipment_id is None:
            if event.shipment_external_ref is not None:
                shipment = db.scalar(
                    select(Shipment).where(Shipment.external_ref == event.shipment_external_ref)
                )
                if shipment is not None:
                    event.shipment_id = shipment.id

        if event.shipment_id is None:
            event.last_error = "Shipment not linked"
            event.processed_at = None
            if event.attempts >= 3:
                event.status = "dead_letter"
                dead_lettered += 1
                attempt.outcome = "dead_letter"
            else:
                event.status = "failed"
                failed += 1
                attempt.outcome = "failed"
            attempt.error_message = event.last_error
        else:
            shipment = db.get(Shipment, event.shipment_id)
            if shipment is None:
                event.last_error = "Shipment not linked"
                event.processed_at = None
                if event.attempts >= 3:
                    event.status = "dead_letter"
                    dead_lettered += 1
                    attempt.outcome = "dead_letter"
                else:
                    event.status = "failed"
                    failed += 1
                    attempt.outcome = "failed"
                attempt.error_message = event.last_error
            else:
                if "delivered" in event.event_type:
                    shipment.current_status = "delivered"
                    shipment.delivered_at = utc_now()
                event.status = "processed"
                event.last_error = None
                event.processed_at = utc_now()
                processed += 1

        attempt.finished_at = utc_now()
        db.add(attempt)

    db.commit()
    return ProcessResult(processed=processed, failed=failed, dead_lettered=dead_lettered)


@router.post("/events/{event_id}/retry", response_model=WebhookEventResponse)
def retry_event(
    event_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> WebhookEventResponse:
    stmt = (
        select(WebhookEvent)
        .options(selectinload(WebhookEvent.attempts_list))
        .where(WebhookEvent.id == event_id)
    )
    event = db.scalar(stmt)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook event not found")
    if event.status != "failed" or event.attempts >= 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Event not eligible for retry"
        )

    event.status = "received"
    event.last_error = None
    event.processor_token = None
    event.processed_at = None
    db.commit()
    db.refresh(event)
    return to_webhook_event_response(event)
