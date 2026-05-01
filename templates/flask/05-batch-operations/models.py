# pyright: reportCallIssue=false
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

import importlib

db = importlib.import_module("database").db


class BatchProduct(db.Model):
    __tablename__ = "cookbook_batch_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "sku": self.sku, "name": self.name, "price": self.price, "is_active": self.is_active, "created_at": self.created_at.isoformat()}


class BatchJob(db.Model):
    __tablename__ = "cookbook_batch_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_cnt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_cnt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rows: Mapped[list["BatchJobRow"]] = relationship(back_populates="job")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "job_type": self.job_type, "status": self.status, "total_rows": self.total_rows, "success_cnt": self.success_cnt, "failed_cnt": self.failed_cnt, "created_at": self.created_at.isoformat(), "finished_at": self.finished_at.isoformat() if self.finished_at else None}


class BatchJobRow(db.Model):
    __tablename__ = "cookbook_batch_job_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("cookbook_batch_jobs.id"), nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    job: Mapped["BatchJob"] = relationship(back_populates="rows")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "job_id": self.job_id, "row_index": self.row_index, "sku": self.sku, "payload": self.payload, "status": self.status, "error_message": self.error_message}
