# pyright: reportImplicitRelativeImport=false, reportCallIssue=false, reportArgumentType=false
from __future__ import annotations

import os

from flask import Blueprint, Flask, jsonify, request
from sqlalchemy.exc import IntegrityError

import importlib

db = importlib.import_module("database").db
models_module = importlib.import_module("models")
Document = models_module.Document
Role = models_module.Role
User = models_module.User
UserRole = models_module.UserRole

bp = Blueprint("rbac", __name__, url_prefix="/")


def _payload() -> dict[str, object]:
    payload_value = request.get_json(silent=True)
    return payload_value if isinstance(payload_value, dict) else {}


def _permissions_text(permissions: object) -> str:
    if not isinstance(permissions, list):
        return ""
    cleaned: list[str] = []
    for permission in permissions:
        value = str(permission).strip()
        if value:
            cleaned.append(value)
    return ",".join(cleaned)


def _to_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_user_permissions(user: User, db_session) -> set[str]:
    permissions: set[str] = set()
    user_roles = UserRole.query.filter_by(user_id=user.id).all()
    for user_role in user_roles:
        role = db_session.get(Role, user_role.role_id)
        visited: set[int] = set()
        while role and role.id not in visited:
            visited.add(role.id)
            for permission in role.permissions_text.split(","):
                parsed = permission.strip()
                if parsed:
                    permissions.add(parsed)
            if role.parent_role_id:
                role = db_session.get(Role, role.parent_role_id)
            else:
                break
    return permissions


def check_permission(user: User, document: Document, required_permission: str, db_session) -> bool:
    if document.owner_user_id == user.id:
        return True
    permissions = get_user_permissions(user, db_session)
    return required_permission in permissions or "admin:*" in permissions


def _would_create_cycle(role: Role | None, parent: Role) -> bool:
    if role is None:
        return False

    visited: set[int] = set()
    current: Role | None = parent
    while current is not None:
        if current.id == role.id:
            return True
        if current.id in visited:
            return True
        visited.add(current.id)
        if current.parent_role_id is None:
            break
        current = db.session.get(Role, current.parent_role_id)
    return False


@bp.put("/roles/<string:role_key>")
def put_role(role_key: str):
    payload = _payload()
    name = str(payload.get("name", "")).strip()
    parent_role_key = payload.get("parent_role_key")
    expected_version = payload.get("expected_version")

    if not name:
        return jsonify({"error": "name is required"}), 400

    role = Role.query.filter_by(role_key=role_key).first()

    parent_role = None
    if parent_role_key is not None:
        parent_key = str(parent_role_key).strip()
        if parent_key:
            parent_role = Role.query.filter_by(role_key=parent_key).first()
            if parent_role is None:
                return jsonify({"error": "parent role not found"}), 404
            if parent_key == role_key:
                return jsonify({"error": "role hierarchy cycle detected"}), 400
            if _would_create_cycle(role, parent_role):
                return jsonify({"error": "role hierarchy cycle detected"}), 400

    permissions_text = _permissions_text(payload.get("permissions"))

    if role is None:
        role = Role()
        role.role_key = role_key
        role.name = name
        role.parent_role_id = parent_role.id if parent_role else None
        role.permissions_text = permissions_text
        db.session.add(role)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "duplicate role_key"}), 409
        return jsonify({"role_key": role.role_key, "version": role.version}), 201

    parsed_expected = _to_int(expected_version)
    if parsed_expected is None:
        return jsonify({"error": "stale version"}), 409

    updated = (
        db.session.query(Role)
        .filter(Role.id == role.id, Role.version == parsed_expected)
        .update(
            {
                "name": name,
                "parent_role_id": parent_role.id if parent_role else None,
                "permissions_text": permissions_text,
                "version": Role.version + 1,
            }
        )
    )
    if updated != 1:
        db.session.rollback()
        return jsonify({"error": "stale version"}), 409
    db.session.commit()
    db.session.refresh(role)
    return jsonify({"role_key": role.role_key, "version": role.version}), 200


@bp.post("/users")
def post_users():
    payload = _payload()
    user_key = str(payload.get("user_key", "")).strip()
    display_name = str(payload.get("display_name", "")).strip()
    if not user_key or not display_name:
        return jsonify({"error": "user_key and display_name are required"}), 400

    user = User()
    user.user_key = user_key
    user.display_name = display_name
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "duplicate user_key"}), 409
    return jsonify({"user_key": user.user_key}), 201


@bp.post("/users/<string:user_key>/roles/<string:role_key>")
def post_user_role(user_key: str, role_key: str):
    user = User.query.filter_by(user_key=user_key).first()
    role = Role.query.filter_by(role_key=role_key).first()
    if user is None or role is None:
        return jsonify({"error": "user or role not found"}), 404

    assignment = UserRole()
    assignment.user_id = user.id
    assignment.role_id = role.id
    db.session.add(assignment)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "duplicate role assignment"}), 409
    return jsonify({"user_key": user_key, "role_key": role_key}), 201


@bp.post("/documents")
def post_documents():
    payload = _payload()
    document_key = str(payload.get("document_key", "")).strip()
    owner_user_key = str(payload.get("owner_user_key", "")).strip()
    title = str(payload.get("title", "")).strip()
    body_text = str(payload.get("body_text", "")).strip()
    as_user_key = str(payload.get("as_user_key", "")).strip()

    owner = User.query.filter_by(user_key=owner_user_key).first()
    as_user = User.query.filter_by(user_key=as_user_key).first()
    if owner is None or as_user is None:
        return jsonify({"error": "user not found"}), 404

    synthetic_document = Document()
    synthetic_document.owner_user_id = owner.id
    synthetic_document.document_key = "_"
    synthetic_document.title = "_"
    synthetic_document.body_text = "_"
    if not check_permission(as_user, synthetic_document, "document:write", db.session):
        return jsonify({"error": "forbidden"}), 403

    document = Document()
    document.document_key = document_key
    document.owner_user_id = owner.id
    document.title = title
    document.body_text = body_text
    db.session.add(document)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "duplicate document_key"}), 409
    return jsonify({"document_key": document.document_key, "version": document.version}), 201


@bp.get("/documents/<string:document_key>")
def get_document(document_key: str):
    as_user_key = str(request.args.get("as_user_key", "")).strip()
    as_user = User.query.filter_by(user_key=as_user_key).first()
    document = Document.query.filter_by(document_key=document_key).first()
    if as_user is None or document is None:
        return jsonify({"error": "not found"}), 404

    if not check_permission(as_user, document, "document:read", db.session):
        return jsonify({"error": "forbidden"}), 403

    return (
        jsonify(
            {
                "document_key": document.document_key,
                "owner_user_id": document.owner_user_id,
                "title": document.title,
                "body_text": document.body_text,
                "version": document.version,
            }
        ),
        200,
    )


@bp.put("/documents/<string:document_key>")
def put_document(document_key: str):
    document = Document.query.filter_by(document_key=document_key).first()
    if document is None:
        return jsonify({"error": "document not found"}), 404

    payload = _payload()
    as_user_key = str(payload.get("as_user_key", "")).strip()
    expected_version = payload.get("expected_version")
    as_user = User.query.filter_by(user_key=as_user_key).first()
    if as_user is None:
        return jsonify({"error": "user not found"}), 404

    if not check_permission(as_user, document, "document:write", db.session):
        return jsonify({"error": "forbidden"}), 403

    parsed_expected = _to_int(expected_version)
    if parsed_expected is None:
        return jsonify({"error": "stale version"}), 409

    update_values: dict[str, object] = {}
    if "title" in payload:
        update_values["title"] = str(payload.get("title", "")).strip()
    if "body_text" in payload:
        update_values["body_text"] = str(payload.get("body_text", "")).strip()
    update_values["version"] = Document.version + 1

    updated = (
        db.session.query(Document)
        .filter(Document.id == document.id, Document.version == parsed_expected)
        .update(update_values)
    )
    if updated != 1:
        db.session.rollback()
        return jsonify({"error": "stale version"}), 409
    db.session.commit()
    db.session.refresh(document)
    return jsonify({"document_key": document.document_key, "version": document.version}), 200


def create_app(config: dict[str, object] | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "cubrid+pycubrid://dba@localhost:33000/testdb"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if config:
        app.config.update(config)

    db.init_app(app)
    with app.app_context():
        db.create_all()
    app.register_blueprint(bp)
    return app
