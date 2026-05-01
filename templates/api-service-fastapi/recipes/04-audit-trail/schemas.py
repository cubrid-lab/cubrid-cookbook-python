# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ProfileCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=255)
    bio: str | None = None

class ProfileUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    bio: str | None = None

class ProfileResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    bio: str | None
    version: int
    created_at: datetime
    updated_at: datetime

class ProfileEventResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    event_type: str
    payload: str
    version: int
    created_at: datetime
