from fastapi import APIRouter

from app.api import payments, tariffs, webhooks

api_router = APIRouter()
api_router.include_router(tariffs.router, prefix="/tariffs", tags=["tariffs"])
api_router.include_router(payments.router, prefix="/payments", tags=["payments"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
