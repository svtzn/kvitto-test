from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from app.api.deps import SessionDep
from app.schemas.webhook import BankWebhook, WebhookError, WebhookResult
from app.services.payments import InvalidTransition, PaymentNotFound, change_status

router = APIRouter()


@router.post(
    "/bank",
    response_model=WebhookResult,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Платежа нет"},
        status.HTTP_409_CONFLICT: {"model": WebhookError, "description": "Запрещённый переход"},
    },
)
async def bank_webhook(data: BankWebhook, session: SessionDep) -> WebhookResult | JSONResponse:
    try:
        await change_status(session, data.payment_id, data.status)
    except PaymentNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found") from None
    except InvalidTransition:
        return JSONResponse(WebhookError().model_dump(), status_code=status.HTTP_409_CONFLICT)
    return WebhookResult()
