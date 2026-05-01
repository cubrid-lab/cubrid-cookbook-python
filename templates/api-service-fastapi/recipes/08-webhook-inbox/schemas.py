# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ShipmentCreate(BaseModel):
    external_ref: str = Field(min_length=1, max_length=100)
    carrier: str = Field(min_length=1, max_length=50)

class ShipmentResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    external_ref: str
    carrier: str
    current_status: str
    delivered_at: datetime | None

class WebhookIngest(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    external_event_id: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=50)
    payload: str
    shipment_external_ref: str | None = Field(default=None, min_length=1, max_length=100)

class WebhookAttemptResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    webhook_event_id: int
    attempt_no: int
    started_at: datetime
    finished_at: datetime | None
    outcome: str
    error_message: str | None

class WebhookEventResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    provider: str
    external_event_id: str
    shipment_id: int | None
    event_type: str
    payload: str
    status: str
    attempts: int
    processor_token: str | None
    last_error: str | None
    received_at: datetime
    processed_at: datetime | None
    attempts_list: list[WebhookAttemptResponse] = Field(default_factory=list)

class ProcessRequest(BaseModel):
    processor_token: str = Field(min_length=1, max_length=100)
    max_events: int = Field(default=5, ge=1)

class ProcessResult(BaseModel):
    processed: int
    failed: int
    dead_lettered: int
