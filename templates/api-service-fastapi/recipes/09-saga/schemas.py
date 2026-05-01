from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InventoryCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    available_qty: int = Field(gt=0)


class PaymentCreate(BaseModel):
    client_id: str = Field(min_length=1, max_length=64)
    available_cents: int = Field(gt=0)


class OrderCreate(BaseModel):
    order_key: str = Field(min_length=1, max_length=64)
    client_id: str = Field(min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(gt=0)
    total_cents: int = Field(gt=0)


class RecoverRequest(BaseModel):
    timeout_seconds: int = Field(default=300, gt=0)


class OrderOut(BaseModel):
    order_key: str
    client_id: str
    sku: str
    quantity: int
    total_cents: int
    state: str
    failure_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SagaStepOut(BaseModel):
    step_name: str
    status: str
    attempt_count: int
    compensation_attempt_count: int
    detail_text: str | None
    executed_at: datetime | None
    compensated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
