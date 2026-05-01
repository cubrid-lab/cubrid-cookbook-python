from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import importlib

from fastapi import FastAPI

database = importlib.import_module("database")
routes = importlib.import_module("routes")
Base = database.Base
engine = database.engine
router = routes.router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(
    title="FastAPI Reservation Scheduling",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Reservation scheduling recipe"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router)
