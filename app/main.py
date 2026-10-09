from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router
from app.db import SessionFactory, engine
from app.seed import seed_tariffs


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with SessionFactory() as session:
        await seed_tariffs(session)
    yield
    await engine.dispose()


app = FastAPI(title="Kvitto", lifespan=lifespan)
app.include_router(api_router)
