from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router
from app.db import engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # TODO: seed тарифов (идемпотентный upsert)
    yield
    await engine.dispose()


app = FastAPI(title="Kvitto", lifespan=lifespan)
app.include_router(api_router)
