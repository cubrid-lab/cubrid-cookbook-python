# pyright: reportCallIssue=false
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

import importlib

db = importlib.import_module("database").db


class ReviewCase(db.Model):
    __tablename__ = "cookbook_review_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    claimed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    notes: Mapped[list["ReviewNote"]] = relationship(back_populates="case", cascade="all, delete-orphan")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "customer_email": self.customer_email,
            "subject": self.subject,
            "body": self.body,
            "priority": self.priority,
            "status": self.status,
            "claimed_by": self.claimed_by,
            "lease_expires_at": self.lease_expires_at.isoformat() if self.lease_expires_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
        }


class ReviewNote(db.Model):
    __tablename__ = "cookbook_review_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(Integer, ForeignKey("cookbook_review_cases.id"), nullable=False)
    author: Mapped[str] = mapped_column(String(80), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    case: Mapped["ReviewCase"] = relationship(back_populates="notes")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "case_id": self.case_id, "author": self.author, "body": self.body, "created_at": self.created_at.isoformat()}
