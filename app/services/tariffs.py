from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tariff


async def list_tariffs(session: AsyncSession) -> Sequence[Tariff]:
    return (await session.scalars(select(Tariff).order_by(Tariff.price, Tariff.id))).all()
