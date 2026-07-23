"""Category management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[schemas.CategoryRead])
def list_categories(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[schemas.CategoryRead]:
    return crud.category_repository.list(db, skip=skip, limit=limit)


@router.get("/{category_id}", response_model=schemas.CategoryRead)
def get_category(category_id: int, db: Session = Depends(get_db)) -> schemas.CategoryRead:
    return crud.category_repository.get(db, category_id)


@router.post("", response_model=schemas.CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: schemas.CategoryCreate, db: Session = Depends(get_db)
) -> schemas.CategoryRead:
    return crud.category_repository.create(db, payload)


@router.put("/{category_id}", response_model=schemas.CategoryRead)
def update_category(
    category_id: int,
    payload: schemas.CategoryUpdate,
    db: Session = Depends(get_db),
) -> schemas.CategoryRead:
    return crud.category_repository.update(db, category_id, payload)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, db: Session = Depends(get_db)) -> Response:
    crud.category_repository.delete(db, category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
