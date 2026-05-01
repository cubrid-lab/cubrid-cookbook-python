# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CatalogItemSync(BaseModel):
    external_sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    price: int = Field(gt=0)
    available: int = Field(ge=0, le=1)

class CatalogSyncRequest(BaseModel):
    source: str = Field(min_length=1, max_length=100)
    items: list[CatalogItemSync] = Field(min_length=1)

class CatalogItemResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    external_sku: str
    name: str
    price: int
    available: int
    source_version: int
    last_synced_at: datetime

class SyncRunResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    source: str
    status: str
    total_rows: int
    created_cnt: int
    updated_cnt: int
    failed_cnt: int
    created_at: datetime
    finished_at: datetime | None
