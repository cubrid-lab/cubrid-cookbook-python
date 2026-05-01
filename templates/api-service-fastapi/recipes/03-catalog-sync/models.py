# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def utc_now() -> datetime:
    return datetime.utcnow()

class CatalogItem(Base):
    __tablename__: str = "cookbook_catalog_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    external_sku: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    available: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

class SyncRun(Base):
    __tablename__: str = "cookbook_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_cnt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_cnt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_cnt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
