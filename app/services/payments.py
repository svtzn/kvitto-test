import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentStatus, Tariff
from app.promo import get_discount_percent, normalize_promo_code
from app.schemas.payment import PaymentCreate
from app.services.pricing import calc_price
from app.services.transitions import can_transition


class UnknownTariff(Exception):
    def __init__(self, tariff_id: str) -> None:
        super().__init__(f"Unknown tariff: {tariff_id!r}")
        self.tariff_id = tariff_id


class PaymentNotFound(Exception):
    def __init__(self, payment_id: uuid.UUID) -> None:
        super().__init__(f"Payment not found: {payment_id}")
        self.payment_id = payment_id


class InvalidTransition(Exception):
    def __init__(self, current: PaymentStatus, new: PaymentStatus) -> None:
        super().__init__(f"Invalid transition: {current} -> {new}")
        self.current = current
        self.new = new


# --- создание ---


async def create_payment(
    session: AsyncSession, data: PaymentCreate, idempotency_key: str | None
) -> tuple[Payment, bool]:
    """Создаёт платёж. Возвращает (платёж, создан ли он этим вызовом).

    Raises:
        UnknownTariff, UnknownPromoCode
    """
    if idempotency_key is not None:
        existing = await get_by_idempotency_key(session, idempotency_key)
        if existing is not None:
            return existing, False

    payment = await _build_payment(session, data, idempotency_key)
    return await _save_new_payment(session, payment)


async def get_by_idempotency_key(session: AsyncSession, key: str) -> Payment | None:
    return await session.scalar(select(Payment).where(Payment.idempotency_key == key))


async def _build_payment(
    session: AsyncSession, data: PaymentCreate, idempotency_key: str | None
) -> Payment:
    tariff = await session.get(Tariff, data.tariff_id)
    if tariff is None:
        raise UnknownTariff(data.tariff_id)

    promo_code = None
    discount_percent = 0
    if data.promo_code is not None:
        discount_percent = get_discount_percent(data.promo_code)
        promo_code = normalize_promo_code(data.promo_code)

    months = int(data.installment_months) if data.installment_months is not None else None
    price = calc_price(tariff.price, discount_percent, months)

    return Payment(
        tariff_id=tariff.id,
        amount=price.amount,
        discount=price.discount,
        method=data.method,
        installment_months=months,
        schedule=price.schedule,
        email=data.email,
        promo_code=promo_code,
        idempotency_key=idempotency_key,
    )


async def _save_new_payment(session: AsyncSession, payment: Payment) -> tuple[Payment, bool]:
    key = payment.idempotency_key
    session.add(payment)
    try:
        await session.commit()
    except IntegrityError:
        # гонка: параллельный запрос с тем же ключом успел закоммитить раньше
        await session.rollback()
        if key is not None:
            existing = await get_by_idempotency_key(session, key)
            if existing is not None:
                return existing, False
        raise
    return payment, True


# --- чтение ---


async def get_payment(session: AsyncSession, payment_id: uuid.UUID) -> Payment | None:
    return await session.get(Payment, payment_id)


async def list_payments(
    session: AsyncSession, email: str | None = None, status: PaymentStatus | None = None
) -> Sequence[Payment]:
    stmt = select(Payment).order_by(Payment.created_at.desc(), Payment.id.desc())
    if email is not None:
        stmt = stmt.where(func.lower(Payment.email) == email.lower())
    if status is not None:
        stmt = stmt.where(Payment.status == status)
    return (await session.scalars(stmt)).all()


# --- смена статуса ---


async def change_status(
    session: AsyncSession, payment_id: uuid.UUID, new_status: PaymentStatus
) -> None:
    """Атомарно меняет статус платежа.

    Строка блокируется через SELECT … FOR UPDATE до конца транзакции, поэтому
    параллельные вебхуки проверяют переход по уже зафиксированному статусу.

    Raises:
        PaymentNotFound, InvalidTransition
    """
    payment = await session.get(Payment, payment_id, with_for_update=True, populate_existing=True)
    if payment is None:
        await session.rollback()
        raise PaymentNotFound(payment_id)
    current = payment.status  # после rollback атрибуты объекта истекают
    if not can_transition(current, new_status):
        await session.rollback()
        raise InvalidTransition(current, new_status)
    payment.status = new_status
    await session.commit()
