# pyright: reportCallIssue=false
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

import importlib

db = importlib.import_module("database").db


class Category(db.Model):
    __tablename__ = "cookbook_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cookbook_categories.id"), nullable=True)
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    parent: Mapped["Category | None"] = relationship("Category", remote_side=[id], back_populates="children")
    children: Mapped[list["Category"]] = relationship("Category", back_populates="parent")
    articles: Mapped[list["Article"]] = relationship(back_populates="category")

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat(),
        }


class Article(db.Model):
    __tablename__ = "cookbook_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("cookbook_categories.id"), nullable=False)
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    category: Mapped[Category] = relationship(back_populates="articles")

    def to_dict(self) -> dict[str, str | int]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body or "",
            "category_id": self.category_id,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat(),
        }
