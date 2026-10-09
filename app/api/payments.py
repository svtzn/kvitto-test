import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from pydantic import BeforeValidator

from app.api.deps import SessionDep
from app.models import Payment, PaymentStatus
from app.promo import UnknownPromoCode
from app.schemas.payment import PaymentCreate, PaymentRead
from app.services.payments import UnknownTariff, create_payment, get_payment, list_payments

router = APIRouter()


def _blank_to_none(value: object) -> object:
    """Пустой или пробельный query-параметр считается отсутствующим."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


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


@router.get("", response_model=list[PaymentRead])
async def get_payments(
    session: SessionDep,
    email: Annotated[str | None, BeforeValidator(_blank_to_none), Query()] = None,
    payment_status: Annotated[
        PaymentStatus | None, BeforeValidator(_blank_to_none), Query(alias="status")
    ] = None,
) -> Sequence[Payment]:
    return await list_payments(session, email=email, status=payment_status)


@router.get("/{payment_id}", response_model=PaymentRead)
async def get_payment_by_id(payment_id: uuid.UUID, session: SessionDep) -> Payment:
    payment = await get_payment(session, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return payment
