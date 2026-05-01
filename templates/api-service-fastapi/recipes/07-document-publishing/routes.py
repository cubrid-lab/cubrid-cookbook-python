# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Document, DocumentRevision
from schemas import (
    DocumentCreate,
    DocumentDetailResponse,
    DocumentResponse,
    DraftCreate,
    RevisionResponse,
)

router = APIRouter()


def get_document_or_404(document_id: int, db: Session) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


def list_document_revisions(document_id: int, db: Session) -> list[DocumentRevision]:
    stmt = (
        select(DocumentRevision)
        .where(DocumentRevision.document_id == document_id)
        .order_by(DocumentRevision.revision_no.asc())
    )
    return cast(list[DocumentRevision], db.scalars(stmt).all())


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreate,
    db: Annotated[Session, Depends(get_db)],
) -> DocumentResponse:
    document = Document(slug=payload.slug, title=payload.title, version=1)
    db.add(document)
    try:
        db.flush()
        revision = DocumentRevision(
            document_id=document.id,
            revision_no=1,
            title=payload.title,
            body=payload.body,
            source_revision_id=None,
            created_by=payload.created_by,
        )
        db.add(revision)
        db.flush()
        document.current_draft_revision_id = revision.id
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document already exists")

    db.refresh(document)
    return DocumentResponse.model_validate(document)


@router.post(
    "/{document_id}/drafts", response_model=RevisionResponse, status_code=status.HTTP_201_CREATED
)
def create_draft_revision(
    document_id: int,
    payload: DraftCreate,
    expected_version: Annotated[int, Query(ge=1)],
    db: Annotated[Session, Depends(get_db)],
) -> RevisionResponse:
    document = get_document_or_404(document_id, db)
    if document.version != expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale version")

    max_revision_stmt = select(func.max(DocumentRevision.revision_no)).where(
        DocumentRevision.document_id == document_id
    )
    max_revision_no = db.scalar(max_revision_stmt)
    next_revision_no = (max_revision_no or 0) + 1

    revision = DocumentRevision(
        document_id=document_id,
        revision_no=next_revision_no,
        title=payload.title,
        body=payload.body,
        source_revision_id=None,
        created_by=payload.created_by,
    )
    db.add(revision)
    try:
        db.flush()

        result = db.execute(
            update(Document)
            .where(Document.id == document_id, Document.version == expected_version)
            .values(
                title=payload.title,
                current_draft_revision_id=revision.id,
                version=expected_version + 1,
            )
        )
        if cast(CursorResult[object], result).rowcount == 0:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale version")

        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Revision conflict")

    db.refresh(revision)
    return RevisionResponse.model_validate(revision)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: int, db: Annotated[Session, Depends(get_db)]
) -> DocumentDetailResponse:
    document = get_document_or_404(document_id, db)
    revisions = list_document_revisions(document_id, db)

    published_revision = None
    if document.published_revision_id is not None:
        stmt = select(DocumentRevision).where(DocumentRevision.id == document.published_revision_id)
        published_revision = db.scalar(stmt)

    return DocumentDetailResponse(
        document=DocumentResponse.model_validate(document),
        revisions=[RevisionResponse.model_validate(revision) for revision in revisions],
        published_revision=(
            RevisionResponse.model_validate(published_revision)
            if published_revision is not None
            else None
        ),
    )


@router.get("/{document_id}/revisions", response_model=list[RevisionResponse])
def get_document_revisions(
    document_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> list[RevisionResponse]:
    _ = get_document_or_404(document_id, db)
    revisions = list_document_revisions(document_id, db)
    return [RevisionResponse.model_validate(revision) for revision in revisions]


@router.post("/{document_id}/publish", response_model=DocumentResponse)
def publish_document(
    document_id: int,
    expected_version: Annotated[int, Query(ge=1)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentResponse:
    document = get_document_or_404(document_id, db)
    if document.current_draft_revision_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No draft revision")
    if document.version != expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale version")

    result = db.execute(
        update(Document)
        .where(Document.id == document_id, Document.version == expected_version)
        .values(
            published_revision_id=document.current_draft_revision_id,
            version=expected_version + 1,
        )
    )
    if cast(CursorResult[object], result).rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale version")

    db.commit()
    db.refresh(document)
    return DocumentResponse.model_validate(document)


@router.post("/{document_id}/restore/{revision_id}", response_model=RevisionResponse)
def restore_revision_as_new_draft(
    document_id: int,
    revision_id: int,
    created_by: Annotated[str, Query(min_length=1, max_length=100)],
    expected_version: Annotated[int, Query(ge=1)],
    db: Annotated[Session, Depends(get_db)],
) -> RevisionResponse:
    document = get_document_or_404(document_id, db)
    if document.version != expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale version")

    source_stmt = select(DocumentRevision).where(
        DocumentRevision.id == revision_id,
        DocumentRevision.document_id == document_id,
    )
    source_revision = db.scalar(source_stmt)
    if source_revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")

    max_revision_stmt = select(func.max(DocumentRevision.revision_no)).where(
        DocumentRevision.document_id == document_id
    )
    max_revision_no = db.scalar(max_revision_stmt)
    next_revision_no = (max_revision_no or 0) + 1

    new_revision = DocumentRevision(
        document_id=document_id,
        revision_no=next_revision_no,
        title=source_revision.title,
        body=source_revision.body,
        source_revision_id=source_revision.id,
        created_by=created_by,
    )
    db.add(new_revision)
    try:
        db.flush()

        result = db.execute(
            update(Document)
            .where(Document.id == document_id, Document.version == expected_version)
            .values(
                title=new_revision.title,
                current_draft_revision_id=new_revision.id,
                version=expected_version + 1,
            )
        )
        if cast(CursorResult[object], result).rowcount == 0:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale version")

        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Revision conflict")

    db.refresh(new_revision)
    return RevisionResponse.model_validate(new_revision)


@router.get("/by-slug/{slug}", response_model=DocumentResponse)
def get_document_by_slug(slug: str, db: Annotated[Session, Depends(get_db)]) -> DocumentResponse:
    stmt = select(Document).where(Document.slug == slug)
    document = db.scalar(stmt)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentResponse.model_validate(document)
