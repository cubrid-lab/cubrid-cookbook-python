from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CookbookCategory(Base):
    __tablename__ = "cookbook_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    val: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    items: Mapped[list[CookbookItem]] = relationship(
        "CookbookItem",
        back_populates="category",
        cascade="all, delete-orphan",
        # passive_deletes removed — CUBRID FK cascade support varies (issue #33).
    )

class CookbookItem(Base):
    __tablename__ = "cookbook_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    val: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cnt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cookbook_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category: Mapped[CookbookCategory] = relationship("CookbookCategory", back_populates="items")
