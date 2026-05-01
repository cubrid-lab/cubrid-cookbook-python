# pyright: reportCallIssue=false
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

import importlib

db = importlib.import_module("database").db


class Warehouse(db.Model):
    __tablename__ = "cookbook_warehouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    stock_items: Mapped[list["StockItem"]] = relationship(back_populates="warehouse")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "code": self.code, "name": self.name, "created_at": self.created_at.isoformat()}


class StockItem(db.Model):
    __tablename__ = "cookbook_stock_items"
    __table_args__ = (UniqueConstraint("warehouse_id", "sku", name="uq_stock_item_warehouse_sku"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(Integer, ForeignKey("cookbook_warehouses.id"), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    on_hand_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    warehouse: Mapped["Warehouse"] = relationship(back_populates="stock_items")
    movements: Mapped[list["StockMovement"]] = relationship(back_populates="stock_item")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "warehouse_id": self.warehouse_id, "sku": self.sku, "product_name": self.product_name, "on_hand_qty": self.on_hand_qty}


class StockMovement(db.Model):
    __tablename__ = "cookbook_stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("cookbook_stock_items.id"), nullable=False)
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    qty_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    stock_item: Mapped["StockItem"] = relationship(back_populates="movements")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "stock_item_id": self.stock_item_id, "movement_type": self.movement_type, "qty_delta": self.qty_delta, "reference": self.reference, "note": self.note, "created_at": self.created_at.isoformat()}
