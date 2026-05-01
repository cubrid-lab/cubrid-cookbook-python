from __future__ import annotations
# pyright: reportGeneralTypeIssues=false, reportImplicitRelativeImport=false

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import ApiClient, ClientRateWindow
from schemas import (
    ClientCreate,
    ClientInfo,
    ConsumeRequest,
    ConsumeResponse,
    PolicyUpdate,
    QuotaResponse,
    ResetRequest,
)

router = APIRouter()


def utcnow() -> datetime:
    return datetime.utcnow()


def _rotate_window_if_needed(window: ClientRateWindow, now: datetime, window_seconds: int) -> None:
    elapsed = (now - window.current_window_start).total_seconds()
    if elapsed < window_seconds:
        return

    if elapsed >= window_seconds * 2:
        window.previous_window_start = None
        window.previous_count = 0
    else:
        window.previous_window_start = window.current_window_start
        window.previous_count = window.current_count

    window.current_window_start = now
    window.current_count = 0


def _weighted_count(window: ClientRateWindow, now: datetime, window_seconds: int) -> int:
    elapsed_in_current = (now - window.current_window_start).total_seconds()
    overlap_fraction = max(0.0, 1 - (elapsed_in_current / window_seconds))
    return window.current_count + int(window.previous_count * overlap_fraction)


def _reset_seconds(window: ClientRateWindow, now: datetime, window_seconds: int) -> int:
    reset_at = window.current_window_start + timedelta(seconds=window_seconds)
    return max(0, int((reset_at - now).total_seconds()))


@router.post("/clients", response_model=ClientInfo, status_code=status.HTTP_201_CREATED)
def create_client(payload: ClientCreate, db: Session = Depends(get_db)) -> ApiClient:
    now = utcnow()
    client = ApiClient(
        client_key=payload.client_key,
        limit_per_window=payload.limit_per_window,
        window_seconds=payload.window_seconds,
        burst_allowance=payload.burst_allowance,
    )
    db.add(client)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="client_key already exists") from exc

    window = ClientRateWindow(
        client_id=client.id,
        current_window_start=now,
        current_count=0,
        previous_window_start=None,
        previous_count=0,
    )
    db.add(window)
    db.commit()
    db.refresh(client)
    return client


@router.put("/clients/{client_key}/policy", response_model=ClientInfo)
def update_policy(
    client_key: str, payload: PolicyUpdate, db: Session = Depends(get_db)
) -> ApiClient:
    client = db.query(ApiClient).filter(ApiClient.client_key == client_key).first()
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")

    result = db.execute(
        update(ApiClient)
        .where(ApiClient.id == client.id, ApiClient.version == payload.expected_version)
        .values(
            limit_per_window=payload.limit_per_window,
            window_seconds=payload.window_seconds,
            burst_allowance=payload.burst_allowance,
            version=ApiClient.version + 1,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="stale version")

    db.commit()
    db.refresh(client)
    client = db.query(ApiClient).filter(ApiClient.client_key == client_key).first()
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")
    return client


@router.post("/clients/{client_key}/consume", response_model=ConsumeResponse)
def consume(
    client_key: str,
    payload: ConsumeRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> ConsumeResponse:
    now = utcnow()
    client = db.query(ApiClient).filter(ApiClient.client_key == client_key).first()
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")

    window = db.query(ClientRateWindow).filter(ClientRateWindow.client_id == client.id).first()
    if window is None:
        raise HTTPException(status_code=404, detail="rate window not found")

    _rotate_window_if_needed(window, now, client.window_seconds)
    weighted_before = _weighted_count(window, now, client.window_seconds)
    allowed_limit = client.limit_per_window + client.burst_allowance

    if weighted_before + payload.cost > allowed_limit:
        retry_after = _reset_seconds(window, now, client.window_seconds)
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    expected_version = window.version
    update_stmt = (
        update(ClientRateWindow)
        .where(ClientRateWindow.id == window.id, ClientRateWindow.version == expected_version)
        .values(
            current_count=ClientRateWindow.current_count + payload.cost,
            version=ClientRateWindow.version + 1,
            last_seen_at=now,
            updated_at=now,
            current_window_start=window.current_window_start,
            previous_window_start=window.previous_window_start,
            previous_count=window.previous_count,
        )
    )
    result = db.execute(update_stmt)
    updated_rows = int((result).rowcount) if isinstance(result, CursorResult) else 0
    if updated_rows != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="version conflict")

    db.commit()
    db.refresh(window)

    weighted_after = _weighted_count(window, now, client.window_seconds)
    remaining = max(0, allowed_limit - weighted_after)
    reset_at = window.current_window_start + timedelta(seconds=client.window_seconds)

    response.headers["X-RateLimit-Limit"] = str(client.limit_per_window)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(_reset_seconds(window, now, client.window_seconds))

    return ConsumeResponse(
        allowed=True,
        weighted_count=weighted_after,
        remaining=remaining,
        reset_at=reset_at,
        window_version=window.version,
    )


@router.get("/clients/{client_key}/quota", response_model=QuotaResponse)
def get_quota(client_key: str, db: Session = Depends(get_db)) -> QuotaResponse:
    now = utcnow()
    client = db.query(ApiClient).filter(ApiClient.client_key == client_key).first()
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")

    window = db.query(ClientRateWindow).filter(ClientRateWindow.client_id == client.id).first()
    if window is None:
        raise HTTPException(status_code=404, detail="rate window not found")

    expected_version = window.version
    prev_current_window_start = window.current_window_start
    prev_current_count = window.current_count
    prev_previous_window_start = window.previous_window_start
    prev_previous_count = window.previous_count
    _rotate_window_if_needed(window, now, client.window_seconds)

    if (
        window.current_window_start != prev_current_window_start
        or window.current_count != prev_current_count
        or window.previous_window_start != prev_previous_window_start
        or window.previous_count != prev_previous_count
    ):
        result = db.execute(
            update(ClientRateWindow)
            .where(ClientRateWindow.id == window.id, ClientRateWindow.version == expected_version)
            .values(
                current_window_start=window.current_window_start,
                current_count=window.current_count,
                previous_window_start=window.previous_window_start,
                previous_count=window.previous_count,
                version=ClientRateWindow.version + 1,
                last_seen_at=now,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="version conflict")
        db.commit()
        db.refresh(window)

    weighted = _weighted_count(window, now, client.window_seconds)
    remaining = max(0, client.limit_per_window + client.burst_allowance - weighted)

    return QuotaResponse(
        client_key=client.client_key,
        limit_per_window=client.limit_per_window,
        burst_allowance=client.burst_allowance,
        window_seconds=client.window_seconds,
        current_window_start=window.current_window_start,
        current_count=window.current_count,
        previous_window_start=window.previous_window_start,
        previous_count=window.previous_count,
        weighted_count=weighted,
        remaining=remaining,
        window_version=window.version,
    )


@router.post("/clients/{client_key}/reset", response_model=QuotaResponse)
def reset_client(
    client_key: str, payload: ResetRequest, db: Session = Depends(get_db)
) -> QuotaResponse:
    now = utcnow()
    client = db.query(ApiClient).filter(ApiClient.client_key == client_key).first()
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")

    window = db.query(ClientRateWindow).filter(ClientRateWindow.client_id == client.id).first()
    if window is None:
        raise HTTPException(status_code=404, detail="rate window not found")
    if window.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="stale version")

    window.current_window_start = now
    window.current_count = 0
    window.previous_window_start = None
    window.previous_count = 0
    window.version += 1
    window.last_seen_at = now
    db.commit()
    db.refresh(window)

    return QuotaResponse(
        client_key=client.client_key,
        limit_per_window=client.limit_per_window,
        burst_allowance=client.burst_allowance,
        window_seconds=client.window_seconds,
        current_window_start=window.current_window_start,
        current_count=window.current_count,
        previous_window_start=window.previous_window_start,
        previous_count=window.previous_count,
        weighted_count=0,
        remaining=client.limit_per_window + client.burst_allowance,
        window_version=window.version,
    )


@router.get("/clients/{client_key}", response_model=ClientInfo)
def get_client(client_key: str, db: Session = Depends(get_db)) -> ApiClient:
    client = db.query(ApiClient).filter(ApiClient.client_key == client_key).first()
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")
    return client
