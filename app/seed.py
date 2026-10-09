from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tariff

TARIFFS: list[dict[str, str | int]] = [
    {"id": "basic", "title": "Базовый", "price": 990000},
    {"id": "standard", "title": "Стандарт", "price": 1990000},
    {"id": "premium", "title": "Премиум", "price": 2990000},
]


async def seed_tariffs(session: AsyncSession) -> None:
    stmt = insert(Tariff).values(TARIFFS)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Tariff.id],
        set_={"title": stmt.excluded.title, "price": stmt.excluded.price},
    )
    await session.execute(stmt)
    await session.commit()
