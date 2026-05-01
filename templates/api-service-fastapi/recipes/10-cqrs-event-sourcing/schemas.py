from datetime import datetime

from pydantic import BaseModel, Field


class OpenAccountRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)
    owner_name: str = Field(min_length=1, max_length=120)


class AmountCommandRequest(BaseModel):
    amount_cents: int = Field(gt=0)
    expected_sequence_no: int = Field(ge=0)


class RebuildRequest(BaseModel):
    from_scratch: int = Field(default=0, ge=0, le=1)


class AccountReadModelResponse(BaseModel):
    account_id: str
    owner_name: str
    balance_cents: int
    state: str
    last_sequence_no: int
    version: int


class EventResponse(BaseModel):
    sequence_no: int
    event_type: str
    payload: dict[str, object]
    metadata: dict[str, object] | None
    created_at: datetime


class SnapshotResponse(BaseModel):
    aggregate_id: str
    last_sequence_no: int
    version: int


class CommandResultResponse(BaseModel):
    account_id: str
    event_type: str
    sequence_no: int
    balance_cents: int
    last_sequence_no: int
