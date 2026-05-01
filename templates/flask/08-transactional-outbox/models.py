# pyright: reportCallIssue=false
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

import importlib

db = importlib.import_module("database").db


class Invoice(db.Model):
    __tablename__ = "cookbook_invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "customer_email": self.customer_email, "total_cents": self.total_cents, "status": self.status, "sent_at": self.sent_at.isoformat() if self.sent_at else None, "created_at": self.created_at.isoformat()}


class OutboxMessage(db.Model):
    __tablename__ = "cookbook_outbox_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    leased_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    leased_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts_list: Mapped[list["OutboxAttempt"]] = relationship(back_populates="message")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "topic": self.topic, "aggregate_type": self.aggregate_type, "aggregate_id": self.aggregate_id, "event_type": self.event_type, "payload": self.payload, "status": self.status, "attempts": self.attempts, "next_attempt_at": self.next_attempt_at.isoformat(), "leased_until": self.leased_until.isoformat() if self.leased_until else None, "leased_by": self.leased_by, "idempotency_key": self.idempotency_key, "last_error": self.last_error, "created_at": self.created_at.isoformat(), "sent_at": self.sent_at.isoformat() if self.sent_at else None}


class OutboxAttempt(db.Model):
    __tablename__ = "cookbook_outbox_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outbox_message_id: Mapped[int] = mapped_column(Integer, ForeignKey("cookbook_outbox_messages.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped["OutboxMessage"] = relationship(back_populates="attempts_list")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "outbox_message_id": self.outbox_message_id, "started_at": self.started_at.isoformat(), "finished_at": self.finished_at.isoformat() if self.finished_at else None, "outcome": self.outcome, "error_message": self.error_message}
