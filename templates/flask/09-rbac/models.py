from __future__ import annotations

from datetime import datetime, timezone
import importlib

db = importlib.import_module("database").db


def naive_utc_now() -> datetime:
    """Naive UTC timestamp; CUBRID DATETIME columns store no timezone."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    role_key = db.Column(db.String(64), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    parent_role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=True, index=True)
    permissions_text = db.Column(db.Text, nullable=False, default="")
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=naive_utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=naive_utc_now, onupdate=naive_utc_now
    )


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    user_key = db.Column(db.String(64), nullable=False, unique=True, index=True)
    display_name = db.Column(db.String(120), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=naive_utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=naive_utc_now, onupdate=naive_utc_now
    )


class UserRole(db.Model):
    __tablename__ = "user_roles"
    __table_args__ = (db.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False, index=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=naive_utc_now)


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    document_key = db.Column(db.String(64), nullable=False, unique=True, index=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    body_text = db.Column(db.Text, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=naive_utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=naive_utc_now, onupdate=naive_utc_now
    )
