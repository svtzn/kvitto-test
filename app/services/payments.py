import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentMethod, PaymentStatus, Tariff
from app.promo import get_discount_percent
from app.schemas.payment import PaymentCreate
from app.services.pricing import build_schedule, calc_discount
from app.services.transitions import can_transition


class UnknownTariff(Exception):
    def __init__(self, tariff_id: str) -> None:
        super().__init__(f"Unknown tariff: {tariff_id!r}")
        self.tariff_id = tariff_id


async def get_by_idempotency_key(session: AsyncSession, key: str) -> Payment | None:
    return await session.scalar(select(Payment).where(Payment.idempotency_key == key))


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

    tariff = await session.get(Tariff, data.tariff_id)
    if tariff is None:
        raise UnknownTariff(data.tariff_id)

    promo_code = None
    discount = 0
    if data.promo_code is not None:
        percent = get_discount_percent(data.promo_code)
        promo_code = data.promo_code.strip().upper()
        discount = calc_discount(tariff.price, percent)
    amount = tariff.price - discount

    months = None
    schedule = None
    if data.method is PaymentMethod.INSTALLMENT:
        assert data.installment_months is not None  # гарантирует PaymentCreate
        months = int(data.installment_months)
        schedule = build_schedule(amount, months)

    payment = Payment(
        tariff_id=tariff.id,
        amount=amount,
        discount=discount,
        method=data.method,
        installment_months=months,
        schedule=schedule,
        email=data.email,
        promo_code=promo_code,
        idempotency_key=idempotency_key,
    )
    session.add(payment)
    try:
        await session.commit()
    except IntegrityError:
        # гонка: параллельный запрос с тем же ключом успел закоммитить раньше
        await session.rollback()
        if idempotency_key is not None:
            existing = await get_by_idempotency_key(session, idempotency_key)
            if existing is not None:
                return existing, False
        raise
    return payment, True


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


class PaymentNotFound(Exception):
    def __init__(self, payment_id: uuid.UUID) -> None:
        super().__init__(f"Payment not found: {payment_id}")
        self.payment_id = payment_id


class InvalidTransition(Exception):
    def __init__(self, current: PaymentStatus, new: PaymentStatus) -> None:
        super().__init__(f"Invalid transition: {current} -> {new}")
        self.current = current
        self.new = new


async def change_status(
    session: AsyncSession, payment_id: uuid.UUID, new_status: PaymentStatus
) -> Payment:
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
    return payment
