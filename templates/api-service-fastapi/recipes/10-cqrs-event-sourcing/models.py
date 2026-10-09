from datetime import datetime, timezone
import importlib

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

try:
    from .database import Base
except ImportError:
    Base = importlib.import_module("database").Base


def naive_utc_now() -> datetime:
    """Naive UTC timestamp; CUBRID DATETIME columns store no timezone."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EventStore(Base):
    __tablename__ = "event_store"
    __table_args__ = (
        UniqueConstraint("aggregate_id", "sequence_no", name="uq_event_store_aggregate_seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=naive_utc_now, index=True
    )


class AggregateSnapshot(Base):
    __tablename__ = "aggregate_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    last_sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    state_text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=naive_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=naive_utc_now, onupdate=naive_utc_now
    )


class AccountReadModel(Base):
    __tablename__ = "account_read_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    owner_name: Mapped[str] = mapped_column(String(120), nullable=False)
    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="open", index=True)
    last_sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=naive_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=naive_utc_now, onupdate=naive_utc_now
    )
