from __future__ import annotations

import importlib
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

database = importlib.import_module("database")
models = importlib.import_module("models")
schemas = importlib.import_module("schemas")

get_db = database.get_db
Reservation = models.Reservation
Resource = models.Resource
WaitlistEntry = models.WaitlistEntry
CancelResult = schemas.CancelResult
ReservationCreate = schemas.ReservationCreate
ReservationOut = schemas.ReservationOut
ResourceCreate = schemas.ResourceCreate
ResourceOut = schemas.ResourceOut
WaitlistCreate = schemas.WaitlistCreate
WaitlistEntryOut = schemas.WaitlistEntryOut

router = APIRouter()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _has_overlap(db: Session, resource_id: int, start_at: datetime, end_at: datetime) -> bool:
    conflict = (
        db.query(Reservation)
        .filter(
            Reservation.resource_id == resource_id,
            Reservation.state == "active",
            Reservation.start_at < end_at,
            Reservation.end_at > start_at,
        )
        .first()
    )
    return conflict is not None


def _validate_interval(start_at: datetime, end_at: datetime) -> None:
    if start_at >= end_at:
        raise HTTPException(status_code=400, detail="invalid interval")


def _serialize_on_resource(db: Session, resource: Resource) -> None:
    expected_version = resource.version
    result = db.execute(
        update(Resource)
        .where(Resource.id == resource.id, Resource.version == expected_version)
        .values(version=Resource.version + 1, updated_at=utcnow())
    )
    updated_rows = int(result.rowcount) if isinstance(result, CursorResult) else 0
    if updated_rows != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="resource version conflict")
    db.refresh(resource)


@router.post("/resources", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
def create_resource(payload: ResourceCreate, db: Annotated[Session, Depends(get_db)]) -> Resource:
    resource = Resource(
        resource_key=payload.resource_key,
        name=payload.name,
        slot_minutes=payload.slot_minutes,
    )
    db.add(resource)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="resource_key already exists") from exc
    db.refresh(resource)
    return resource


@router.post("/reservations", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def create_reservation(
    payload: ReservationCreate, db: Annotated[Session, Depends(get_db)]
) -> Reservation:
    _validate_interval(payload.start_at, payload.end_at)
    resource = db.query(Resource).filter(Resource.resource_key == payload.resource_key).first()
    if resource is None:
        raise HTTPException(status_code=404, detail="resource not found")

    _serialize_on_resource(db, resource)

    if _has_overlap(db, resource.id, payload.start_at, payload.end_at):
        db.rollback()
        raise HTTPException(status_code=409, detail="reservation overlap")

    reservation = Reservation(
        reservation_key=payload.reservation_key,
        resource_id=resource.id,
        requester_id=payload.requester_id,
        start_at=payload.start_at,
        end_at=payload.end_at,
        state="active",
    )
    db.add(reservation)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="reservation_key already exists") from exc
    db.refresh(reservation)
    return reservation


@router.get("/reservations/{reservation_key}", response_model=ReservationOut)
def get_reservation(reservation_key: str, db: Annotated[Session, Depends(get_db)]) -> Reservation:
    reservation = (
        db.query(Reservation).filter(Reservation.reservation_key == reservation_key).first()
    )
    if reservation is None:
        raise HTTPException(status_code=404, detail="reservation not found")
    return reservation


@router.get("/resources/{resource_key}/reservations", response_model=list[ReservationOut])
def list_reservations(
    resource_key: str,
    from_at: Annotated[datetime, Query(...)],
    to_at: Annotated[datetime, Query(...)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Reservation]:
    _validate_interval(from_at, to_at)
    resource = db.query(Resource).filter(Resource.resource_key == resource_key).first()
    if resource is None:
        raise HTTPException(status_code=404, detail="resource not found")

    reservations = (
        db.query(Reservation)
        .filter(
            Reservation.resource_id == resource.id,
            Reservation.start_at < to_at,
            Reservation.end_at > from_at,
        )
        .order_by(Reservation.start_at.asc(), Reservation.id.asc())
        .all()
    )
    return reservations


@router.post("/reservations/{reservation_key}/cancel", response_model=CancelResult)
def cancel_reservation(
    reservation_key: str, db: Annotated[Session, Depends(get_db)]
) -> CancelResult:
    reservation = (
        db.query(Reservation).filter(Reservation.reservation_key == reservation_key).first()
    )
    if reservation is None:
        raise HTTPException(status_code=404, detail="reservation not found")
    if reservation.state != "active":
        raise HTTPException(status_code=400, detail="reservation already cancelled")

    resource = db.query(Resource).filter(Resource.id == reservation.resource_id).first()
    if resource is None:
        raise HTTPException(status_code=404, detail="resource not found")

    _serialize_on_resource(db, resource)

    expected_version = reservation.version
    now = utcnow()
    result = db.execute(
        update(Reservation)
        .where(
            Reservation.id == reservation.id,
            Reservation.version == expected_version,
            Reservation.state == "active",
        )
        .values(
            state="cancelled",
            cancelled_at=now,
            version=Reservation.version + 1,
            updated_at=now,
        )
    )
    updated_rows = int(result.rowcount) if isinstance(result, CursorResult) else 0
    if updated_rows != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="stale reservation version")

    promoted_key: str | None = None
    waitlist_entries = (
        db.query(WaitlistEntry)
        .filter(
            WaitlistEntry.resource_id == resource.id,
            WaitlistEntry.state == "waiting",
        )
        .order_by(WaitlistEntry.created_at.asc(), WaitlistEntry.id.asc())
        .all()
    )

    for entry in waitlist_entries:
        if _has_overlap(db, resource.id, entry.desired_start_at, entry.desired_end_at):
            continue

        promoted = Reservation(
            reservation_key=f"promoted-{entry.id}",
            resource_id=resource.id,
            requester_id=entry.requester_id,
            start_at=entry.desired_start_at,
            end_at=entry.desired_end_at,
            state="active",
        )
        db.add(promoted)
        db.flush()

        entry.state = "promoted"
        entry.promoted_reservation_id = promoted.id
        entry.version += 1
        promoted_key = promoted.reservation_key
        break

    db.commit()
    return CancelResult(
        reservation_key=reservation_key,
        state="cancelled",
        promoted_reservation_key=promoted_key,
    )


@router.post(
    "/resources/{resource_key}/waitlist",
    response_model=WaitlistEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def add_waitlist_entry(
    resource_key: str,
    payload: WaitlistCreate,
    db: Annotated[Session, Depends(get_db)],
) -> WaitlistEntry:
    _validate_interval(payload.desired_start_at, payload.desired_end_at)
    resource = db.query(Resource).filter(Resource.resource_key == resource_key).first()
    if resource is None:
        raise HTTPException(status_code=404, detail="resource not found")

    entry = WaitlistEntry(
        resource_id=resource.id,
        requester_id=payload.requester_id,
        desired_start_at=payload.desired_start_at,
        desired_end_at=payload.desired_end_at,
        state="waiting",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/resources/{resource_key}/waitlist", response_model=list[WaitlistEntryOut])
def list_waitlist(
    resource_key: str, db: Annotated[Session, Depends(get_db)]
) -> list[WaitlistEntry]:
    resource = db.query(Resource).filter(Resource.resource_key == resource_key).first()
    if resource is None:
        raise HTTPException(status_code=404, detail="resource not found")
    return (
        db.query(WaitlistEntry)
        .filter(
            WaitlistEntry.resource_id == resource.id,
            and_(WaitlistEntry.state.in_(["waiting", "promoted"])),
        )
        .order_by(WaitlistEntry.created_at.asc(), WaitlistEntry.id.asc())
        .all()
    )
