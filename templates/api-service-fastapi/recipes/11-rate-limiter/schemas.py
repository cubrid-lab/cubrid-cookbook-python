from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ClientCreate(BaseModel):
    client_key: str = Field(min_length=1, max_length=64)
    limit_per_window: int = Field(gt=0)
    window_seconds: int = Field(gt=0)
    burst_allowance: int = Field(ge=0, default=0)


class PolicyUpdate(BaseModel):
    limit_per_window: int = Field(gt=0)
    window_seconds: int = Field(gt=0)
    burst_allowance: int = Field(ge=0, default=0)
    expected_version: int = Field(ge=1)


class ConsumeRequest(BaseModel):
    cost: int = Field(default=1, gt=0)


class ResetRequest(BaseModel):
    expected_version: int = Field(ge=1)


class ClientInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    client_key: str
    plan_name: str
    limit_per_window: int
    window_seconds: int
    burst_allowance: int
    version: int
    created_at: datetime
    updated_at: datetime


class QuotaResponse(BaseModel):
    client_key: str
    limit_per_window: int
    burst_allowance: int
    window_seconds: int
    current_window_start: datetime
    current_count: int
    previous_window_start: datetime | None
    previous_count: int
    weighted_count: int
    remaining: int
    window_version: int


class ConsumeResponse(BaseModel):
    allowed: bool
    weighted_count: int
    remaining: int
    reset_at: datetime
    window_version: int
