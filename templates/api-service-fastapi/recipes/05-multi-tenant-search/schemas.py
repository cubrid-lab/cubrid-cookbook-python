# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=50)

class TenantResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    created_at: datetime

class ContactCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    city: str | None = Field(default=None, max_length=100)
    status: str = Field(default="active", min_length=1, max_length=20)

class ContactUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    city: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, min_length=1, max_length=20)

class ContactResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    first_name: str
    last_name: str
    email: str
    city: str | None
    status: str
    created_at: datetime

class ContactCursorList(BaseModel):
    items: list[ContactResponse]
    next_cursor: int | None
    has_more: bool
