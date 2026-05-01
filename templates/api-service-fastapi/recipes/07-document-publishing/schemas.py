# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class DocumentCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    created_by: str = Field(min_length=1, max_length=100)

class DraftCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    created_by: str = Field(min_length=1, max_length=100)

class DocumentResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    version: int
    current_draft_revision_id: int | None
    published_revision_id: int | None
    created_at: datetime
    updated_at: datetime

class RevisionResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    revision_no: int
    title: str
    body: str
    source_revision_id: int | None
    created_by: str
    created_at: datetime

class DocumentDetailResponse(BaseModel):
    document: DocumentResponse
    revisions: list[RevisionResponse]
    published_revision: RevisionResponse | None
