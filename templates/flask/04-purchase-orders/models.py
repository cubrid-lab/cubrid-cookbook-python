# pyright: reportCallIssue=false
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

import importlib

db = importlib.import_module("database").db


class Supplier(db.Model):
    __tablename__ = "cookbook_suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="supplier")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "name": self.name, "code": self.code, "created_at": self.created_at.isoformat()}


class PurchaseOrder(db.Model):
    __tablename__ = "cookbook_purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(Integer, ForeignKey("cookbook_suppliers.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supplier: Mapped["Supplier"] = relationship(back_populates="orders")
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(back_populates="order", cascade="all, delete-orphan")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "supplier_id": self.supplier_id,
            "status": self.status,
            "notes": self.notes,
            "version": self.version,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "fulfilled_at": self.fulfilled_at.isoformat() if self.fulfilled_at else None,
            "created_at": self.created_at.isoformat(),
        }


class PurchaseOrderLine(db.Model):
    __tablename__ = "cookbook_purchase_order_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("cookbook_purchase_orders.id"), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[int] = mapped_column(Integer, nullable=False)
    received_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    order: Mapped["PurchaseOrder"] = relationship(back_populates="lines")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "order_id": self.order_id, "sku": self.sku, "description": self.description, "quantity": self.quantity, "unit_cost": self.unit_cost, "received_qty": self.received_qty}
