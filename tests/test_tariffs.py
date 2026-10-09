from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tariff
from app.seed import seed_tariffs

EXPECTED = [
    {"id": "basic", "title": "Базовый", "price": 990000},
    {"id": "standard", "title": "Стандарт", "price": 1990000},
    {"id": "premium", "title": "Премиум", "price": 2990000},
]


async def test_get_tariffs(client: AsyncClient) -> None:
    response = await client.get("/tariffs")

    assert response.status_code == 200
    assert response.json() == EXPECTED


async def test_seed_is_idempotent_and_restores_values(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await db_session.execute(update(Tariff).where(Tariff.id == "basic").values(price=1, title="x"))
    await db_session.commit()

    await seed_tariffs(db_session)
    await seed_tariffs(db_session)

    rows = (await db_session.execute(select(Tariff.id, Tariff.title, Tariff.price))).all()
    assert sorted(rows, key=lambda r: r.price) == [tuple(t.values()) for t in EXPECTED]
    assert (await client.get("/tariffs")).json() == EXPECTED
