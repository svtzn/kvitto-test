import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentMethod, PaymentStatus

T0 = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


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
