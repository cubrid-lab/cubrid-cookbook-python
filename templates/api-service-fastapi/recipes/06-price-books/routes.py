# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import PriceBookEntry, PriceProduct
from schemas import (
    PriceEntryCreate,
    PriceEntryResponse,
    PriceProductCreate,
    PriceProductResponse,
    SupersedeRequest,
)

router = APIRouter()


def _to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def ensure_valid_range(starts_at: datetime, ends_at: datetime | None) -> None:
    if ends_at is not None and starts_at >= ends_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="starts_at must be before ends_at",
        )


def has_overlap(
    db: Session,
    *,
    product_id: int,
    channel: str,
    currency: str,
    starts_at: datetime,
    ends_at: datetime | None,
    exclude_entry_id: int | None = None,
) -> bool:
    stmt = select(PriceBookEntry.id).where(
        PriceBookEntry.product_id == product_id,
        PriceBookEntry.channel == channel,
        PriceBookEntry.currency == currency,
    )

    if ends_at is None:
        overlap_predicate = or_(
            PriceBookEntry.ends_at.is_(None),
            PriceBookEntry.ends_at > starts_at,
        )
    else:
        overlap_predicate = and_(
            PriceBookEntry.starts_at < ends_at,
            or_(
                PriceBookEntry.ends_at.is_(None),
                PriceBookEntry.ends_at > starts_at,
            ),
        )

    stmt = stmt.where(overlap_predicate)

    if exclude_entry_id is not None:
        stmt = stmt.where(PriceBookEntry.id != exclude_entry_id)

    return db.scalar(stmt.limit(1)) is not None


@router.post("/products", response_model=PriceProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: PriceProductCreate,
    db: Annotated[Session, Depends(get_db)],
) -> PriceProductResponse:
    product = PriceProduct(sku=payload.sku, name=payload.name, active=1)
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU already exists")
    db.refresh(product)
    return PriceProductResponse.model_validate(product)


@router.post("/prices", response_model=PriceEntryResponse, status_code=status.HTTP_201_CREATED)
def create_price_entry(
    payload: PriceEntryCreate,
    db: Annotated[Session, Depends(get_db)],
) -> PriceEntryResponse:
    starts_at = _to_naive_utc(payload.starts_at)
    ends_at = _to_naive_utc(payload.ends_at) if payload.ends_at is not None else None
    ensure_valid_range(starts_at, ends_at)

    product = db.get(PriceProduct, payload.product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if has_overlap(
        db,
        product_id=payload.product_id,
        channel=payload.channel,
        currency=payload.currency,
        starts_at=starts_at,
        ends_at=ends_at,
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Overlapping price range")

    entry = PriceBookEntry(
        product_id=payload.product_id,
        channel=payload.channel,
        currency=payload.currency,
        amount_cents=payload.amount_cents,
        starts_at=starts_at,
        ends_at=ends_at,
        version=1,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Price entry conflict",
        )
    db.refresh(entry)
    return PriceEntryResponse.model_validate(entry)


@router.get("/products/{product_id}/price", response_model=PriceEntryResponse)
def get_price_as_of(
    product_id: int,
    channel: Annotated[str, Query(min_length=1, max_length=30)],
    currency: Annotated[str, Query(min_length=3, max_length=3)],
    at: datetime,
    db: Annotated[Session, Depends(get_db)],
) -> PriceEntryResponse:
    at = _to_naive_utc(at)
    stmt = (
        select(PriceBookEntry)
        .where(
            PriceBookEntry.product_id == product_id,
            PriceBookEntry.channel == channel,
            PriceBookEntry.currency == currency,
            PriceBookEntry.starts_at <= at,
            or_(PriceBookEntry.ends_at.is_(None), PriceBookEntry.ends_at > at),
        )
        .order_by(PriceBookEntry.starts_at.desc())
    )
    entry = db.scalar(stmt)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price not found")
    return PriceEntryResponse.model_validate(entry)


@router.get("/products/{product_id}/prices", response_model=list[PriceEntryResponse])
def list_product_prices(
    product_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> list[PriceEntryResponse]:
    stmt = (
        select(PriceBookEntry)
        .where(PriceBookEntry.product_id == product_id)
        .order_by(PriceBookEntry.starts_at.asc(), PriceBookEntry.id.asc())
    )
    entries = db.scalars(stmt).all()
    return [PriceEntryResponse.model_validate(entry) for entry in entries]


@router.post("/prices/{entry_id}/supersede", response_model=PriceEntryResponse, status_code=201)
def supersede_price_entry(
    entry_id: int,
    payload: SupersedeRequest,
    db: Annotated[Session, Depends(get_db)],
) -> PriceEntryResponse:
    effective_at = _to_naive_utc(payload.effective_at)
    current = db.get(PriceBookEntry, entry_id)
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price entry not found")
    if current.ends_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Price entry already closed"
        )
    if effective_at <= current.starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="effective_at must be after starts_at",
        )

    if has_overlap(
        db,
        product_id=current.product_id,
        channel=current.channel,
        currency=current.currency,
        starts_at=effective_at,
        ends_at=None,
        exclude_entry_id=current.id,
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Overlapping price range")

    result = db.execute(
        update(PriceBookEntry)
        .where(
            PriceBookEntry.id == current.id,
            PriceBookEntry.version == current.version,
            PriceBookEntry.ends_at.is_(None),
        )
        .values(ends_at=effective_at, version=current.version + 1)
    )
    if cast(CursorResult[object], result).rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale version")

    next_entry = PriceBookEntry(
        product_id=current.product_id,
        channel=current.channel,
        currency=current.currency,
        amount_cents=payload.new_amount_cents,
        starts_at=effective_at,
        ends_at=None,
        version=current.version + 1,
    )
    db.add(next_entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Price entry conflict")
    db.refresh(next_entry)
    return PriceEntryResponse.model_validate(next_entry)


@router.patch("/prices/{entry_id}/close", response_model=PriceEntryResponse)
def close_price_entry(
    entry_id: int,
    effective_at: Annotated[datetime, Body(embed=True)],
    expected_version: Annotated[int, Body(embed=True, ge=1)],
    db: Annotated[Session, Depends(get_db)],
) -> PriceEntryResponse:
    effective_at = _to_naive_utc(effective_at)
    entry = db.get(PriceBookEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price entry not found")
    if entry.ends_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Price entry already closed"
        )
    if effective_at <= entry.starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="effective_at must be after starts_at",
        )

    result = db.execute(
        update(PriceBookEntry)
        .where(
            PriceBookEntry.id == entry_id,
            PriceBookEntry.version == expected_version,
            PriceBookEntry.ends_at.is_(None),
        )
        .values(ends_at=effective_at, version=expected_version + 1)
    )
    if cast(CursorResult[object], result).rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale version")

    db.commit()
    refreshed = db.get(PriceBookEntry, entry_id)
    if refreshed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price entry not found")
    return PriceEntryResponse.model_validate(refreshed)
