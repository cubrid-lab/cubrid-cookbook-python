# pyright: reportCallIssue=false
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import cast

from flask import Blueprint, Flask, jsonify, request
from sqlalchemy import select

import importlib

db = importlib.import_module("database").db

_models = importlib.import_module("models")
Article = _models.Article
Category = _models.Category

bp = Blueprint("categories", __name__, url_prefix="/api/categories")

def _category_or_404(category_id: int) -> Category:
    category = db.session.get(Category, category_id)
    if category is None:
        raise LookupError("Category not found.")
    return category

def _is_include_deleted_enabled() -> bool:
    return request.args.get("include_deleted") == "1"

def _json_payload() -> Mapping[str, object]:
    payload_value = request.get_json(silent=True)
    if isinstance(payload_value, dict):
        return cast(dict[str, object], payload_value)
    return {}

@bp.get("")
def list_categories():
    stmt = select(Category).order_by(Category.id.asc())
    if not _is_include_deleted_enabled():
        stmt = stmt.where(Category.is_deleted == 0)
    categories = db.session.execute(stmt).scalars().all()
    return jsonify([category.to_dict() for category in categories])

@bp.post("")
def create_category():
    payload = _json_payload()
    name = str(payload.get("name", "")).strip()
    parent_id_value = payload.get("parent_id")
    if not name:
        return jsonify({"error": "name is required"}), 400
    parent_id: int | None = None
    if parent_id_value is not None:
        if not isinstance(parent_id_value, int | str):
            return jsonify({"error": "parent_id must be an integer"}), 400
        try:
            parent_id = int(parent_id_value)
        except (TypeError, ValueError):
            return jsonify({"error": "parent_id must be an integer"}), 400
        parent = db.session.get(Category, parent_id)
        if parent is None:
            return jsonify({"error": "Parent category not found."}), 404
        if parent.is_deleted == 1:
            return jsonify({"error": "Cannot create child under a deleted parent."}), 400
    category = Category()
    category.name = name
    category.parent_id = parent_id
    db.session.add(category)
    db.session.commit()
    return jsonify(category.to_dict()), 201

@bp.get("/<int:category_id>")
def get_category(category_id: int):
    try:
        category = _category_or_404(category_id)
    except LookupError:
        return jsonify({"error": "Category not found."}), 404
    if category.is_deleted == 1:
        return jsonify({"error": "Category not found."}), 404
    children = [child.to_dict() for child in category.children if child.is_deleted == 0]
    articles = [article.to_dict() for article in category.articles if article.is_deleted == 0]
    return jsonify({**category.to_dict(), "children": children, "articles": articles})

@bp.delete("/<int:category_id>")
def soft_delete_category(category_id: int):
    try:
        category = _category_or_404(category_id)
    except LookupError:
        return jsonify({"error": "Category not found."}), 404
    active_children = [child for child in category.children if child.is_deleted == 0]
    if active_children:
        return jsonify({"error": "Cannot delete category with active children. Delete or reassign children first."}), 409
    category.is_deleted = 1
    for article in category.articles:
        article.is_deleted = 1
    db.session.commit()
    return jsonify(category.to_dict())

@bp.post("/<int:category_id>/restore")
def restore_category(category_id: int):
    try:
        category = _category_or_404(category_id)
    except LookupError:
        return jsonify({"error": "Category not found."}), 404
    category.is_deleted = 0
    for article in category.articles:
        article.is_deleted = 0
    db.session.commit()
    return jsonify(category.to_dict())

@bp.post("/<int:category_id>/articles")
def create_article(category_id: int):
    category = db.session.get(Category, category_id)
    if category is None or category.is_deleted == 1:
        return jsonify({"error": "Category not found."}), 404
    payload = _json_payload()
    title = str(payload.get("title", "")).strip()
    body = str(payload.get("body", "")).strip() or None
    if not title:
        return jsonify({"error": "title is required"}), 400
    article = Article()
    article.title = title
    article.body = body
    article.category_id = category.id
    db.session.add(article)
    db.session.commit()
    return jsonify(article.to_dict()), 201

@bp.get("/<int:category_id>/articles")
def list_articles(category_id: int):
    category = db.session.get(Category, category_id)
    if category is None or category.is_deleted == 1:
        return jsonify({"error": "Category not found."}), 404
    articles = db.session.execute(select(Article).where(Article.category_id == category_id, Article.is_deleted == 0).order_by(Article.id.asc())).scalars().all()
    return jsonify([article.to_dict() for article in articles])

@bp.delete("/<int:category_id>/articles/<int:article_id>")
def soft_delete_article(category_id: int, article_id: int):
    category = db.session.get(Category, category_id)
    if category is None or category.is_deleted == 1:
        return jsonify({"error": "Category not found."}), 404
    article = db.session.get(Article, article_id)
    if article is None or article.category_id != category.id:
        return jsonify({"error": "Article not found."}), 404
    article.is_deleted = 1
    db.session.commit()
    return jsonify(article.to_dict())

def create_app(config=None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "cubrid+pycubrid://dba@localhost:33000/testdb")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if config:
        app.config.update(config)
    db.init_app(app)
    with app.app_context():
        db.create_all()
    app.register_blueprint(bp)
    return app
