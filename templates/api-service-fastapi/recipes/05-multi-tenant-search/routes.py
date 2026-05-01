# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Contact, Tenant
from schemas import (
    ContactCreate,
    ContactCursorList,
    ContactResponse,
    ContactUpdate,
    TenantCreate,
    TenantResponse,
)

router = APIRouter()


def get_tenant_or_404(tenant_id: int, db: Session) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(payload: TenantCreate, db: Annotated[Session, Depends(get_db)]) -> TenantResponse:
    tenant = Tenant(name=payload.name, slug=payload.slug)
    db.add(tenant)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant already exists")
    db.refresh(tenant)
    return TenantResponse.model_validate(tenant)


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant_id: int, db: Annotated[Session, Depends(get_db)]) -> TenantResponse:
    tenant = get_tenant_or_404(tenant_id, db)
    return TenantResponse.model_validate(tenant)


@router.post(
    "/{tenant_id}/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED
)
def create_contact(
    tenant_id: int,
    payload: ContactCreate,
    db: Annotated[Session, Depends(get_db)],
) -> ContactResponse:
    _ = get_tenant_or_404(tenant_id, db)
    contact = Contact(
        tenant_id=tenant_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=str(payload.email),
        city=payload.city,
        status=payload.status,
    )
    db.add(contact)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contact email already exists for tenant",
        )
    db.refresh(contact)
    return ContactResponse.model_validate(contact)


@router.get("/{tenant_id}/contacts", response_model=ContactCursorList)
def list_contacts(
    *,
    tenant_id: int,
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    city: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    db: Annotated[Session, Depends(get_db)],
) -> ContactCursorList:
    _ = get_tenant_or_404(tenant_id, db)

    stmt = select(Contact).where(Contact.tenant_id == tenant_id)
    if cursor is not None:
        stmt = stmt.where(Contact.id > cursor)
    if status_filter is not None:
        stmt = stmt.where(Contact.status == status_filter)
    if city is not None:
        stmt = stmt.where(Contact.city == city)
    if q:
        term = f"%{q}%"
        stmt = stmt.where(
            or_(
                Contact.first_name.like(term),
                Contact.last_name.like(term),
                Contact.email.like(term),
            )
        )

    stmt = stmt.order_by(Contact.id.asc()).limit(limit + 1)
    contacts = db.scalars(stmt).all()
    has_more = len(contacts) > limit
    items = contacts[:limit]
    next_cursor = items[-1].id if has_more and items else None

    return ContactCursorList(
        items=[ContactResponse.model_validate(item) for item in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.patch("/{tenant_id}/contacts/{contact_id}", response_model=ContactResponse)
def update_contact(
    tenant_id: int,
    contact_id: int,
    payload: ContactUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> ContactResponse:
    _ = get_tenant_or_404(tenant_id, db)
    stmt = select(Contact).where(Contact.id == contact_id, Contact.tenant_id == tenant_id)
    contact = db.scalar(stmt)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    updates = cast(dict[str, object], payload.model_dump(exclude_unset=True))
    if "email" in updates and updates["email"] is not None:
        updates["email"] = str(updates["email"])
    for field_name, value in updates.items():
        setattr(contact, field_name, value)

    db.add(contact)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contact email already exists for tenant",
        )
    db.refresh(contact)
    return ContactResponse.model_validate(contact)


@router.delete("/{tenant_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(
    tenant_id: int,
    contact_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    _ = get_tenant_or_404(tenant_id, db)
    stmt = select(Contact).where(Contact.id == contact_id, Contact.tenant_id == tenant_id)
    contact = db.scalar(stmt)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    db.delete(contact)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
