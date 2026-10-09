import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models import Payment, PaymentMethod, PaymentStatus
from app.seed import seed_tariffs

T0 = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


async def reset_db(engine: AsyncEngine, session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Очищает таблицы и заново заводит тарифы."""
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE payments, tariffs"))
    async with session_factory() as session:
        await seed_tariffs(session)


async def add_payment(
    session: AsyncSession,
    *,
    email: str = "user@example.com",
    status: PaymentStatus = PaymentStatus.PENDING,
    created_at: datetime = T0,
    payment_id: uuid.UUID | None = None,
) -> Payment:
    payment = Payment(
        id=payment_id or uuid.uuid4(),
        status=status,
        tariff_id="basic",
        amount=990000,
        discount=0,
        method=PaymentMethod.CARD,
        email=email,
        created_at=created_at,
    )
    session.add(payment)
    await session.commit()
    return payment


async def reload_payment(session: AsyncSession, payment_id: uuid.UUID | str) -> Payment:
    """Перечитывает платёж из БД, минуя кэш сессии."""
    session.expire_all()
    return await session.get_one(Payment, uuid.UUID(str(payment_id)))
