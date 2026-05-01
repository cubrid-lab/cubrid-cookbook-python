from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import importlib

from fastapi import FastAPI

try:
    from .database import Base, engine
    from .routes import router
except ImportError:
    database_module = importlib.import_module("database")
    routes_module = importlib.import_module("routes")
    Base = database_module.Base
    engine = database_module.engine
    router = routes_module.router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(
    title="FastAPI CQRS Event Sourcing Recipe",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "CQRS + Event Sourcing recipe"}


app.include_router(router)
