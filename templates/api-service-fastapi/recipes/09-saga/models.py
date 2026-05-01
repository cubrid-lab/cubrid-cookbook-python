# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from datetime import datetime

try:
    from .database import Base
except ImportError:
    from database import Base


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    order_key = Column(String(64), nullable=False, unique=True, index=True)
    client_id = Column(String(64), nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    total_cents = Column(Integer, nullable=False)
    state = Column(String(32), nullable=False, default="pending", index=True)
    failure_reason = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id = Column(Integer, primary_key=True)
    sku = Column(String(64), nullable=False, unique=True, index=True)
    available_qty = Column(Integer, nullable=False)
    reserved_qty = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PaymentAccount(Base):
    __tablename__ = "payment_accounts"
    id = Column(Integer, primary_key=True)
    client_id = Column(String(64), nullable=False, unique=True, index=True)
    available_cents = Column(Integer, nullable=False)
    held_cents = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class SagaStep(Base):
    __tablename__ = "saga_steps"
    __table_args__ = (UniqueConstraint("order_id", "step_name", name="uq_saga_steps_order_step"),)
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    step_name = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="pending", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    compensation_attempt_count = Column(Integer, nullable=False, default=0)
    detail_text = Column(Text, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    compensated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
