from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResourceCreate(BaseModel):
    resource_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    slot_minutes: int = Field(default=30, gt=0)


class ResourceOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    resource_key: str
    name: str
    slot_minutes: int
    version: int
    created_at: datetime
    updated_at: datetime


class ReservationCreate(BaseModel):
    reservation_key: str = Field(min_length=1, max_length=64)
    resource_key: str = Field(min_length=1, max_length=64)
    requester_id: str = Field(min_length=1, max_length=64)
    start_at: datetime
    end_at: datetime

    @field_validator("start_at", "end_at", mode="before")
    @classmethod
    def parse_iso_datetime(cls, value: str | datetime) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                # Convert to UTC then strip tzinfo
                from datetime import timezone
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            return value
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None:
                from datetime import timezone
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError as exc:
            raise ValueError("datetime must be valid ISO format") from exc


class ReservationOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    reservation_key: str
    resource_id: int
    requester_id: str
    start_at: datetime
    end_at: datetime
    state: str
    version: int
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReservationWindowQuery(BaseModel):
    from_at: datetime
    to_at: datetime

    @field_validator("from_at", "to_at", mode="before")
    @classmethod
    def parse_iso_datetime(cls, value: str | datetime) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                from datetime import timezone
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            return value
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None:
                from datetime import timezone
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError as exc:
            raise ValueError("datetime must be valid ISO format") from exc


class WaitlistCreate(BaseModel):
    requester_id: str = Field(min_length=1, max_length=64)
    desired_start_at: datetime
    desired_end_at: datetime

    @field_validator("desired_start_at", "desired_end_at", mode="before")
    @classmethod
    def parse_iso_datetime(cls, value: str | datetime) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                from datetime import timezone
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            return value
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None:
                from datetime import timezone
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError as exc:
            raise ValueError("datetime must be valid ISO format") from exc


class WaitlistEntryOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    resource_id: int
    requester_id: str
    desired_start_at: datetime
    desired_end_at: datetime
    state: str
    version: int
    promoted_reservation_id: int | None
    created_at: datetime
    updated_at: datetime


class CancelResult(BaseModel):
    reservation_key: str
    state: str
    promoted_reservation_key: str | None = None
