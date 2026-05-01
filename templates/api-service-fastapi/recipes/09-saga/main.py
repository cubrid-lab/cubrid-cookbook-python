# pyright: basic
from contextlib import asynccontextmanager

from fastapi import FastAPI

try:
    from .database import Base, engine
    from .routes import router
except ImportError:
    from database import Base, engine
    from routes import router


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="FastAPI Saga Recipe", lifespan=lifespan)
app.include_router(router)
