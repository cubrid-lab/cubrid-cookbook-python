# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def utc_now() -> datetime:
    return datetime.utcnow()

class UserProfile(Base):
    __tablename__: str = "cookbook_user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    events: Mapped[list["ProfileEvent"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )

class ProfileEvent(Base):
    __tablename__: str = "cookbook_profile_events"
    __table_args__: tuple[UniqueConstraint] = (
        UniqueConstraint("profile_id", "version", name="uq_profile_event_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cookbook_user_profiles.id"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    profile: Mapped["UserProfile"] = relationship(back_populates="events")
