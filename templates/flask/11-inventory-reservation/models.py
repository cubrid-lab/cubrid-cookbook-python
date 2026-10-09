from datetime import datetime, timezone

from database import db  # pyright: ignore[reportImplicitRelativeImport]


def naive_utc_now() -> datetime:
    """Naive UTC timestamp; CUBRID DATETIME columns store no timezone."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(64), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    on_hand_qty = db.Column(db.Integer, nullable=False)
    reserved_qty = db.Column(db.Integer, nullable=False, default=0)
    committed_qty = db.Column(db.Integer, nullable=False, default=0)
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=naive_utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=naive_utc_now, onupdate=naive_utc_now
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
    created_at = db.Column(db.DateTime, nullable=False, default=naive_utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=naive_utc_now, onupdate=naive_utc_now
    )


class ExpirySweep(db.Model):
    __tablename__ = "expiry_sweeps"

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False, default=naive_utc_now)
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(32), nullable=False, default="running", index=True)
    expired_count = db.Column(db.Integer, nullable=False, default=0)
    error_text = db.Column(db.Text, nullable=True)
