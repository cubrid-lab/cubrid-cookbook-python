import json
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from sqlalchemy import select, text

from .db import CookbookItem, create_tables, get_session

_tables_initialized = False


def _ensure_tables_initialized() -> None:
    global _tables_initialized
    if not _tables_initialized:
        create_tables()
        _tables_initialized = True

def health_view(_request: HttpRequest) -> JsonResponse:
    _ensure_tables_initialized()
    session = get_session()
    try:
        result = session.execute(text("SELECT 1 AS ok")).scalar_one()
        return JsonResponse({"status": "ok", "db": int(result)})
    finally:
        session.close()


@csrf_exempt
def items_view(request: HttpRequest) -> JsonResponse:
    method = request.method or ""

    if method == "GET":
        _ensure_tables_initialized()
        session = get_session()
        try:
            rows = session.execute(select(CookbookItem).order_by(CookbookItem.id)).scalars().all()
            data = [
                {"id": row.id, "title": row.title, "is_active": int(row.is_active)} for row in rows
            ]
            return JsonResponse({"items": data})
        finally:
            session.close()

    if method == "POST":
        _ensure_tables_initialized()
        raw_body = request.body if request.body else b"{}"
        try:
            body: dict[str, Any] = json.loads(raw_body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid JSON"}, status=400)
        title = str(body.get("title", "")).strip()
        if not title:
            return JsonResponse({"error": "title is required"}, status=400)

        is_active = 1 if bool(body.get("is_active", True)) else 0

        session = get_session()
        try:
            item = CookbookItem(title=title, is_active=is_active)
            session.add(item)
            session.commit()
            session.refresh(item)
            return JsonResponse(
                {"id": item.id, "title": item.title, "is_active": int(item.is_active)},
                status=201,
            )
        finally:
            session.close()

    return JsonResponse({"error": "method not allowed"}, status=405)
