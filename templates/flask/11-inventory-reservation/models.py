from datetime import datetime

from database import db  # pyright: ignore[reportImplicitRelativeImport]


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(64), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    on_hand_qty = db.Column(db.Integer, nullable=False)
    reserved_qty = db.Column(db.Integer, nullable=False, default=0)
    committed_qty = db.Column(db.Integer, nullable=False, default=0)
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class StockReservation(db.Model):
    __tablename__ = "stock_reservations"

    id = db.Column(db.Integer, primary_key=True)
    reservation_key = db.Column(db.String(64), nullable=False, unique=True, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False, index=True)
    client_id = db.Column(db.String(64), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    state = db.Column(db.String(32), nullable=False, default="active", index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    released_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ExpirySweep(db.Model):
    __tablename__ = "expiry_sweeps"

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(32), nullable=False, default="running", index=True)
    expired_count = db.Column(db.Integer, nullable=False, default=0)
    error_text = db.Column(db.Text, nullable=True)
