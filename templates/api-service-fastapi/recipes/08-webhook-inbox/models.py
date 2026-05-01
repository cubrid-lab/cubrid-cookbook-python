# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def utc_now() -> datetime:
    return datetime.utcnow()

class Shipment(Base):
    __tablename__: str = "cookbook_shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    external_ref: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    carrier: Mapped[str] = mapped_column(String(50), nullable=False)
    current_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class WebhookEvent(Base):
    __tablename__: str = "cookbook_webhook_events"
    __table_args__: tuple[UniqueConstraint] = (
        UniqueConstraint("provider", "external_event_id", name="uq_webhook_provider_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    shipment_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("cookbook_shipments.id"),
        nullable=True,
    )
    shipment_external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processor_token: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts_list: Mapped[list["WebhookAttempt"]] = relationship(back_populates="event")

class WebhookAttempt(Base):
    __tablename__: str = "cookbook_webhook_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    webhook_event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cookbook_webhook_events.id"),
        nullable=False,
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    event: Mapped["WebhookEvent"] = relationship(back_populates="attempts_list")
