from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, closing, contextmanager
import os

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
import pycubrid
from pycubrid.connection import Connection
from pycubrid.cursor import Cursor
from starlette.concurrency import run_in_threadpool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await run_in_threadpool(create_table)
    yield


app = FastAPI(title="CUBRID Quickstart API", lifespan=lifespan)


class ItemIn(BaseModel):
    val: str


class ItemOut(ItemIn):
    id: int


def get_conn() -> Connection:
    return pycubrid.connect(
        host=os.environ.get("CUBRID_HOST", "localhost"),
        port=33000,
        database="testdb",
        user="dba",
        password="",
        # Bounded, so /health answers 503 instead of hanging on an unreachable host.
        connect_timeout=10,
    )


@contextmanager
def database_cursor() -> Iterator[Cursor]:
    # Explicit cleanup also covers cursor creation, query, commit and rollback failures.
    with closing(get_conn()) as conn:
        try:
            with closing(conn.cursor()) as cursor:
                yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def create_table() -> None:
    with database_cursor() as cursor:
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS cookbook_quickstart_items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            val VARCHAR(255) NOT NULL
        )
            """
        )


@app.get("/health")
def health(response: Response) -> dict[str, str]:
    # A real round trip, so a running API with an unreachable database reports 503.
    try:
        with database_cursor() as cursor:
            cursor.execute("SELECT 1 FROM db_root")
            cursor.fetchone()
    except Exception:
        response.status_code = 503
        return {"status": "error", "database": "unavailable"}
    return {"status": "ok", "database": "ok"}


@app.get("/items", response_model=list[ItemOut])
def list_items() -> list[ItemOut]:
    with database_cursor() as cursor:
        cursor.execute("SELECT id, val FROM cookbook_quickstart_items ORDER BY id")
        return [ItemOut(id=row[0], val=row[1]) for row in cursor.fetchall()]


@app.post("/items", response_model=ItemOut)
def create_item(item: ItemIn) -> ItemOut:
    with database_cursor() as cursor:
        cursor.execute("INSERT INTO cookbook_quickstart_items (val) VALUES (?)", (item.val,))
        return ItemOut(id=cursor.lastrowid, val=item.val)


@app.get("/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int) -> ItemOut:
    with database_cursor() as cursor:
        cursor.execute("SELECT id, val FROM cookbook_quickstart_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Item not found")
        return ItemOut(id=row[0], val=row[1])
