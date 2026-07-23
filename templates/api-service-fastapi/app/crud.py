from __future__ import annotations

from collections.abc import Mapping
from typing import Generic, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import models

ModelT = TypeVar("ModelT")
CreateSchemaT = TypeVar("CreateSchemaT", bound=BaseModel)
UpdateSchemaT = TypeVar("UpdateSchemaT", bound=BaseModel)


class Repository(Generic[ModelT, CreateSchemaT, UpdateSchemaT]):
    def __init__(self, model: type[ModelT]):
        self.model = model

    def _base_query(self) -> Select[tuple[ModelT]]:
        return select(self.model)

    def get(self, db: Session, entity_id: int) -> ModelT:
        entity = db.get(self.model, entity_id)
        if entity is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        return entity

    def list(self, db: Session, skip: int = 0, limit: int = 100) -> list[ModelT]:
        stmt = self._base_query().offset(skip).limit(limit)
        result = db.execute(stmt)
        return list(result.scalars().all())

    def create(self, db: Session, payload: CreateSchemaT) -> ModelT:
        entity = self.model(**payload.model_dump())
        db.add(entity)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Resource conflicts with existing data",
            ) from exc
        db.refresh(entity)
        return entity

    def update(self, db: Session, entity_id: int, payload: UpdateSchemaT) -> ModelT:
        entity = self.get(db, entity_id)
        updates: Mapping[str, object] = payload.model_dump(exclude_unset=True)
        for field_name, field_val in updates.items():
            setattr(entity, field_name, field_val)

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Resource conflicts with existing data",
            ) from exc
        db.refresh(entity)
        return entity

    def delete(self, db: Session, entity_id: int) -> None:
        entity = self.get(db, entity_id)
        db.delete(entity)
        db.commit()


class ItemRepository(Repository[models.CookbookItem, BaseModel, BaseModel]):
    def __init__(self) -> None:
        super().__init__(models.CookbookItem)

    def _base_query(self) -> Select[tuple[models.CookbookItem]]:
        # Eager-load category to prevent N+1 queries and DetachedInstanceError (issue #33).
        return select(models.CookbookItem).options(selectinload(models.CookbookItem.category))

    def get(self, db: Session, entity_id: int) -> models.CookbookItem:
        # Override to use _base_query for eager loading (issue #33).
        stmt = self._base_query().where(models.CookbookItem.id == entity_id)
        entity = db.execute(stmt).scalar_one_or_none()
        if entity is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
        return entity

    def create(self, db: Session, payload: BaseModel) -> models.CookbookItem:
        category = db.get(models.CookbookCategory, payload.category_id)
        if category is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )
        return super().create(db, payload)

    def update(self, db: Session, entity_id: int, payload: BaseModel) -> models.CookbookItem:
        updates = payload.model_dump(exclude_unset=True)
        category_id = updates.get("category_id")
        if isinstance(category_id, int):
            category = db.get(models.CookbookCategory, category_id)
            if category is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Category not found",
                )
        return super().update(db, entity_id, payload)


class CategoryRepository(Repository[models.CookbookCategory, BaseModel, BaseModel]):
    def __init__(self) -> None:
        super().__init__(models.CookbookCategory)


item_repository = ItemRepository()
category_repository = CategoryRepository()
