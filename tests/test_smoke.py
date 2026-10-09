from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentMethod, PaymentStatus, Tariff


async def test_app_responds(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200


async def test_payment_roundtrip(db_session: AsyncSession) -> None:
    payment = Payment(
        tariff_id="standard",
        amount=1990000,
        discount=0,
        method=PaymentMethod.INSTALLMENT,
        installment_months=3,
        schedule=[663334, 663333, 663333],
        email="user@example.com",
    )
    db_session.add(payment)
    await db_session.commit()
    db_session.expunge_all()

    saved = await db_session.get_one(Payment, payment.id)

    assert saved.status is PaymentStatus.PENDING
    assert saved.method is PaymentMethod.INSTALLMENT
    assert saved.schedule == [663334, 663333, 663333]
    assert saved.created_at.tzinfo is not None


# идёт после test_payment_roundtrip: проверяет, что clean_db очищает данные между тестами
async def test_db_is_seeded_and_clean(db_session: AsyncSession) -> None:
    tariffs = (await db_session.scalars(select(Tariff.id).order_by(Tariff.price))).all()
    payments_count = await db_session.scalar(select(func.count()).select_from(Payment))

    assert tariffs == ["basic", "standard", "premium"]
    assert payments_count == 0
