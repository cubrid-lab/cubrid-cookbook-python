from __future__ import annotations

import importlib
from datetime import datetime, timezone
from typing import ClassVar

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

database = importlib.import_module("database")
Base = database.Base


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Resource(Base):
    __tablename__: ClassVar[str] = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slot_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )


class Reservation(Base):
    __tablename__: ClassVar[str] = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reservation_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resources.id"), nullable=False, index=True
    )
    requester_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )


class WaitlistEntry(Base):
    __tablename__: ClassVar[str] = "waitlist_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resources.id"), nullable=False, index=True
    )
    requester_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    desired_start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    desired_end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="waiting", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    promoted_reservation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )
