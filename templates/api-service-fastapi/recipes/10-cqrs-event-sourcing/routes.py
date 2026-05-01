# pyright: reportGeneralTypeIssues=false, reportArgumentType=false, reportAssignmentType=false
import json
import importlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

try:
    from .database import get_db
    from .models import AccountReadModel, AggregateSnapshot, EventStore
    from .schemas import (
        AccountReadModelResponse,
        AmountCommandRequest,
        CommandResultResponse,
        EventResponse,
        OpenAccountRequest,
        RebuildRequest,
        SnapshotResponse,
    )
except ImportError:
    db_module = importlib.import_module("database")
    model_module = importlib.import_module("models")
    schema_module = importlib.import_module("schemas")
    get_db = db_module.get_db
    AccountReadModel = model_module.AccountReadModel
    AggregateSnapshot = model_module.AggregateSnapshot
    EventStore = model_module.EventStore
    AccountReadModelResponse = schema_module.AccountReadModelResponse
    AmountCommandRequest = schema_module.AmountCommandRequest
    CommandResultResponse = schema_module.CommandResultResponse
    EventResponse = schema_module.EventResponse
    OpenAccountRequest = schema_module.OpenAccountRequest
    RebuildRequest = schema_module.RebuildRequest
    SnapshotResponse = schema_module.SnapshotResponse

router = APIRouter()


def _get_tail_sequence(db: Session, account_id: str) -> int | None:
    stmt = (
        select(EventStore.sequence_no)
        .where(EventStore.aggregate_id == account_id)
        .order_by(EventStore.sequence_no.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def _apply_event(
    state: dict[str, object], event_type: str, payload: dict[str, object]
) -> dict[str, object]:
    next_state = dict(state)
    if event_type == "AccountOpened":
        next_state["account_id"] = payload["account_id"]
        next_state["owner_name"] = payload["owner_name"]
        next_state["balance_cents"] = 0
        next_state["state"] = "open"
    elif event_type == "MoneyDeposited":
        next_state["balance_cents"] = int(next_state.get("balance_cents", 0)) + int(
            payload["amount_cents"]
        )
    elif event_type == "MoneyWithdrawn":
        next_state["balance_cents"] = int(next_state.get("balance_cents", 0)) - int(
            payload["amount_cents"]
        )
    return next_state


def _rehydrate_account(db: Session, account_id: str) -> tuple[dict[str, object] | None, int]:
    snapshot = db.scalar(
        select(AggregateSnapshot).where(AggregateSnapshot.aggregate_id == account_id)
    )
    if snapshot is not None:
        state = json.loads(snapshot.state_text)
        current_seq = snapshot.last_sequence_no
        events = db.scalars(
            select(EventStore)
            .where(
                EventStore.aggregate_id == account_id,
                EventStore.sequence_no > snapshot.last_sequence_no,
            )
            .order_by(EventStore.sequence_no.asc())
        ).all()
    else:
        state = None
        current_seq = 0
        events = db.scalars(
            select(EventStore)
            .where(EventStore.aggregate_id == account_id)
            .order_by(EventStore.sequence_no.asc())
        ).all()

    if not events and state is None:
        return None, 0

    if state is None:
        state = {}

    for event in events:
        payload = json.loads(event.payload_text)
        state = _apply_event(state, event.event_type, payload)
        current_seq = event.sequence_no

    state["last_sequence_no"] = current_seq
    return state, current_seq


def _project_read_model(
    db: Session, account_id: str, state: dict[str, object], sequence_no: int
) -> AccountReadModel:
    read_model = db.scalar(
        select(AccountReadModel).where(AccountReadModel.account_id == account_id)
    )
    if read_model is None:
        read_model = AccountReadModel(
            account_id=account_id,
            owner_name=str(state.get("owner_name", "")),
            balance_cents=int(state.get("balance_cents", 0)),
            state=str(state.get("state", "open")),
            last_sequence_no=sequence_no,
        )
        db.add(read_model)
    else:
        if sequence_no <= read_model.last_sequence_no:
            return read_model
        # Conditional UPDATE with version guard for optimistic concurrency
        original_version = read_model.version
        result = db.execute(
            update(AccountReadModel)
            .where(
                AccountReadModel.id == read_model.id,
                AccountReadModel.version == original_version,
            )
            .values(
                owner_name=str(state.get("owner_name", read_model.owner_name)),
                balance_cents=int(state.get("balance_cents", read_model.balance_cents)),
                state=str(state.get("state", read_model.state)),
                last_sequence_no=sequence_no,
                version=original_version + 1,
            )
        )
        if result.rowcount != 1:  # type: ignore[union-attr]
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Concurrent projection conflict"
            )
        db.refresh(read_model)
    return read_model


def _append_event(
    db: Session,
    account_id: str,
    event_type: str,
    payload: dict[str, object],
    expected_sequence_no: int,
) -> EventStore:
    current_tail = _get_tail_sequence(db, account_id)
    tail = 0 if current_tail is None else current_tail
    if tail != expected_sequence_no:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Stale expected_sequence_no"
        )

    event = EventStore(
        aggregate_id=account_id,
        aggregate_type="Account",
        sequence_no=tail + 1,
        event_type=event_type,
        payload_text=json.dumps(payload),
        metadata_text=json.dumps({"expected_sequence_no": expected_sequence_no}),
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Concurrent write conflict"
        ) from exc
    return event


@router.post("/accounts", response_model=CommandResultResponse, status_code=status.HTTP_201_CREATED)
def open_account(
    payload: OpenAccountRequest, db: Annotated[Session, Depends(get_db)]
) -> CommandResultResponse:
    existing = _get_tail_sequence(db, payload.account_id)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists")

    event = _append_event(
        db=db,
        account_id=payload.account_id,
        event_type="AccountOpened",
        payload={"account_id": payload.account_id, "owner_name": payload.owner_name},
        expected_sequence_no=0,
    )
    state = _apply_event({}, event.event_type, json.loads(event.payload_text))
    read_model = _project_read_model(db, payload.account_id, state, event.sequence_no)
    db.commit()
    db.refresh(read_model)
    return CommandResultResponse(
        account_id=payload.account_id,
        event_type=event.event_type,
        sequence_no=event.sequence_no,
        balance_cents=read_model.balance_cents,
        last_sequence_no=read_model.last_sequence_no,
    )


@router.post("/accounts/{account_id}/deposit", response_model=CommandResultResponse)
def deposit(
    account_id: str,
    payload: AmountCommandRequest,
    db: Annotated[Session, Depends(get_db)],
) -> CommandResultResponse:
    if payload.amount_cents <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="amount_cents must be positive"
        )

    if _get_tail_sequence(db, account_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    event = _append_event(
        db=db,
        account_id=account_id,
        event_type="MoneyDeposited",
        payload={"amount_cents": payload.amount_cents},
        expected_sequence_no=payload.expected_sequence_no,
    )
    state, _ = _rehydrate_account(db, account_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    read_model = _project_read_model(db, account_id, state, event.sequence_no)
    db.commit()
    db.refresh(read_model)
    return CommandResultResponse(
        account_id=account_id,
        event_type=event.event_type,
        sequence_no=event.sequence_no,
        balance_cents=read_model.balance_cents,
        last_sequence_no=read_model.last_sequence_no,
    )


@router.post("/accounts/{account_id}/withdraw", response_model=CommandResultResponse)
def withdraw(
    account_id: str,
    payload: AmountCommandRequest,
    db: Annotated[Session, Depends(get_db)],
) -> CommandResultResponse:
    if payload.amount_cents <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="amount_cents must be positive"
        )

    state, _ = _rehydrate_account(db, account_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    current_balance = int(state.get("balance_cents", 0))
    if payload.amount_cents > current_balance:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Insufficient funds"
        )

    event = _append_event(
        db=db,
        account_id=account_id,
        event_type="MoneyWithdrawn",
        payload={"amount_cents": payload.amount_cents},
        expected_sequence_no=payload.expected_sequence_no,
    )
    state = _apply_event(state, event.event_type, json.loads(event.payload_text))
    read_model = _project_read_model(db, account_id, state, event.sequence_no)
    db.commit()
    db.refresh(read_model)
    return CommandResultResponse(
        account_id=account_id,
        event_type=event.event_type,
        sequence_no=event.sequence_no,
        balance_cents=read_model.balance_cents,
        last_sequence_no=read_model.last_sequence_no,
    )


@router.get("/accounts/{account_id}", response_model=AccountReadModelResponse)
def get_account(
    account_id: str, db: Annotated[Session, Depends(get_db)]
) -> AccountReadModelResponse:
    read_model = db.scalar(
        select(AccountReadModel).where(AccountReadModel.account_id == account_id)
    )
    if read_model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return AccountReadModelResponse.model_validate(read_model, from_attributes=True)


@router.get("/accounts/{account_id}/events", response_model=list[EventResponse])
def list_events(account_id: str, db: Annotated[Session, Depends(get_db)]) -> list[EventResponse]:
    events = db.scalars(
        select(EventStore)
        .where(EventStore.aggregate_id == account_id)
        .order_by(EventStore.sequence_no.asc())
    ).all()
    if not events:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    return [
        EventResponse(
            sequence_no=event.sequence_no,
            event_type=event.event_type,
            payload=json.loads(event.payload_text),
            metadata=None if event.metadata_text is None else json.loads(event.metadata_text),
            created_at=event.created_at,
        )
        for event in events
    ]


@router.post("/accounts/{account_id}/snapshot", response_model=SnapshotResponse)
def create_snapshot(account_id: str, db: Annotated[Session, Depends(get_db)]) -> SnapshotResponse:
    state, tail = _rehydrate_account(db, account_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    snapshot = db.scalar(
        select(AggregateSnapshot).where(AggregateSnapshot.aggregate_id == account_id)
    )
    if snapshot is None:
        snapshot = AggregateSnapshot(
            aggregate_id=account_id,
            aggregate_type="Account",
            last_sequence_no=tail,
            state_text=json.dumps(state),
            version=1,
        )
        db.add(snapshot)
    else:
        original_version = snapshot.version
        rows = (
            db.query(AggregateSnapshot)
            .filter(
                AggregateSnapshot.aggregate_id == account_id,
                AggregateSnapshot.version == original_version,
            )
            .update(
                {
                    AggregateSnapshot.last_sequence_no: tail,
                    AggregateSnapshot.state_text: json.dumps(state),
                    AggregateSnapshot.version: original_version + 1,
                }
            )
        )
        if rows == 0:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Concurrent snapshot update"
            )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Concurrent snapshot update"
        ) from exc

    db.refresh(snapshot)
    return SnapshotResponse(
        aggregate_id=snapshot.aggregate_id,
        last_sequence_no=snapshot.last_sequence_no,
        version=snapshot.version,
    )


@router.post("/accounts/{account_id}/rebuild", response_model=AccountReadModelResponse)
def rebuild_account(
    account_id: str,
    payload: RebuildRequest,
    db: Annotated[Session, Depends(get_db)],
) -> AccountReadModelResponse:
    if payload.from_scratch == 1:
        events = db.scalars(
            select(EventStore)
            .where(EventStore.aggregate_id == account_id)
            .order_by(EventStore.sequence_no.asc())
        ).all()
        if not events:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        state: dict[str, object] = {}
        tail = 0
        for event in events:
            state = _apply_event(state, event.event_type, json.loads(event.payload_text))
            tail = event.sequence_no
    else:
        state, tail = _rehydrate_account(db, account_id)
        if state is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    read_model = _project_read_model(db, account_id, state, tail)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Concurrent rebuild conflict"
        ) from exc
    db.refresh(read_model)
    return AccountReadModelResponse.model_validate(read_model, from_attributes=True)
