from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status

from app.api.deps import SessionDep
from app.models import Payment
from app.promo import UnknownPromoCode
from app.schemas.payment import PaymentCreate, PaymentRead
from app.services.payments import UnknownTariff, create_payment

router = APIRouter()


@router.post(
    "",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"model": PaymentRead, "description": "Ключ уже использован"}},
)
async def post_payment(
    data: PaymentCreate,
    session: SessionDep,
    response: Response,
    idempotency_key: Annotated[str | None, Header(max_length=255)] = None,
) -> Payment:
    if idempotency_key is not None and not idempotency_key.strip():
        idempotency_key = None
    try:
        payment, created = await create_payment(session, data, idempotency_key)
    except UnknownTariff:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown tariff") from None
    except UnknownPromoCode:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown promo code") from None
    if not created:
        response.status_code = status.HTTP_200_OK
    return payment
