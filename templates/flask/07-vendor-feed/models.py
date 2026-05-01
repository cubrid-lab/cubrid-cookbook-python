# pyright: reportCallIssue=false
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

import importlib

db = importlib.import_module("database").db


class ImportBatch(db.Model):
    __tablename__ = "cookbook_import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rows: Mapped[list["ImportRow"]] = relationship(back_populates="batch", cascade="all, delete-orphan")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "vendor_name": self.vendor_name, "source_filename": self.source_filename, "status": self.status, "uploaded_at": self.uploaded_at.isoformat(), "validated_at": self.validated_at.isoformat() if self.validated_at else None, "promoted_at": self.promoted_at.isoformat() if self.promoted_at else None}


class ImportRow(db.Model):
    __tablename__ = "cookbook_import_rows"
    __table_args__ = (UniqueConstraint("batch_id", "row_no", name="uq_import_rows_batch_row_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(Integer, ForeignKey("cookbook_import_batches.id"), nullable=False)
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    external_sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    promoted_product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    batch: Mapped["ImportBatch"] = relationship(back_populates="rows")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "batch_id": self.batch_id, "row_no": self.row_no, "external_sku": self.external_sku, "name": self.name, "price_cents": self.price_cents, "raw_payload": self.raw_payload, "validation_status": self.validation_status, "error_code": self.error_code, "error_message": self.error_message, "promoted_product_id": self.promoted_product_id}


class CatalogProduct(db.Model):
    __tablename__ = "cookbook_catalog_products"
    __table_args__ = (UniqueConstraint("vendor_name", "external_sku", name="uq_catalog_product_vendor_sku"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    external_sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "vendor_name": self.vendor_name, "external_sku": self.external_sku, "name": self.name, "price_cents": self.price_cents, "active": self.active}


class Product(db.Model):
    __tablename__ = "cookbook_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    in_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict[str, str | int]:
        return {"id": self.id, "name": self.name, "description": self.description or "", "price": str(self.price), "category": self.category, "in_stock": self.in_stock, "created_at": self.created_at.isoformat()}
