# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PriceProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)

class PriceProductResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    active: int

class PriceEntryCreate(BaseModel):
    product_id: int
    channel: str = Field(min_length=1, max_length=30)
    currency: str = Field(min_length=3, max_length=3)
    amount_cents: int = Field(gt=0)
    starts_at: datetime
    ends_at: datetime | None = None

class PriceEntryResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    channel: str
    currency: str
    amount_cents: int
    starts_at: datetime
    ends_at: datetime | None
    version: int

class SupersedeRequest(BaseModel):
    new_amount_cents: int = Field(gt=0)
    effective_at: datetime
