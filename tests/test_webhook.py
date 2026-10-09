import asyncio
import itertools
import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models import Payment, PaymentStatus
from tests.helpers import add_payment, reload_payment

ALLOWED = [
    (PaymentStatus.PENDING, PaymentStatus.SUCCEEDED),
    (PaymentStatus.PENDING, PaymentStatus.FAILED),
    (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED),
]
FORBIDDEN = [pair for pair in itertools.product(PaymentStatus, repeat=2) if pair not in ALLOWED]


async def send(client: AsyncClient, payment_id: uuid.UUID | str, status: str) -> Response:
    return await client.post(
        "/webhooks/bank", json={"payment_id": str(payment_id), "status": status}
    )


async def db_status(session: AsyncSession, payment_id: uuid.UUID) -> PaymentStatus:
    return (await reload_payment(session, payment_id)).status


async def api_status(client: AsyncClient, payment_id: uuid.UUID) -> str:
    response = await client.get(f"/payments/{payment_id}")
    assert response.status_code == 200
    status: str = response.json()["status"]
    return status


# --- разрешённые переходы ---


@pytest.mark.parametrize(("current", "new"), ALLOWED, ids=lambda s: str(s))
async def test_allowed_transition(
    client: AsyncClient, db_session: AsyncSession, current: PaymentStatus, new: PaymentStatus
) -> None:
    payment = await add_payment(db_session, status=current)

    response = await send(client, payment.id, new)

    assert response.status_code == 200
    assert response.json() == {"result": "ok"}
    assert await api_status(client, payment.id) == new
    assert await db_status(db_session, payment.id) is new


async def test_full_lifecycle(client: AsyncClient, db_session: AsyncSession) -> None:
    created = await client.post(
        "/payments", json={"tariff_id": "basic", "email": "user@example.com", "method": "sbp"}
    )
    payment_id = uuid.UUID(created.json()["id"])

    assert (await send(client, payment_id, "succeeded")).status_code == 200
    assert (await send(client, payment_id, "refunded")).status_code == 200
    assert await db_status(db_session, payment_id) is PaymentStatus.REFUNDED


# --- запрещённые переходы (обязательный тест 4) ---


@pytest.mark.parametrize(("current", "new"), FORBIDDEN, ids=lambda s: str(s))
async def test_forbidden_transition(
    client: AsyncClient, db_session: AsyncSession, current: PaymentStatus, new: PaymentStatus
) -> None:
    payment = await add_payment(db_session, status=current)

    response = await send(client, payment.id, new)

    assert response.status_code == 409
    assert response.json() == {"error": "invalid_transition"}
    assert await api_status(client, payment.id) == current
    assert await db_status(db_session, payment.id) is current


async def test_repeated_webhook_is_conflict(client: AsyncClient, db_session: AsyncSession) -> None:
    payment = await add_payment(db_session)

    first = await send(client, payment.id, "succeeded")
    second = await send(client, payment.id, "succeeded")

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json() == {"error": "invalid_transition"}
    assert await api_status(client, payment.id) == "succeeded"


# --- 404 / 422 ---


async def test_unknown_payment(client: AsyncClient) -> None:
    response = await send(client, uuid.uuid4(), "succeeded")

    assert response.status_code == 404
    assert response.json() == {"detail": "Payment not found"}


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"payment_id": "not-a-uuid", "status": "succeeded"}, id="bad-uuid"),
        pytest.param({"payment_id": str(uuid.uuid4()), "status": "paid"}, id="unknown-status"),
        pytest.param({"payment_id": str(uuid.uuid4()), "status": ""}, id="empty-status"),
        pytest.param({"status": "succeeded"}, id="no-payment-id"),
        pytest.param({"payment_id": str(uuid.uuid4())}, id="no-status"),
    ],
)
async def test_invalid_body(client: AsyncClient, payload: dict[str, Any]) -> None:
    response = await client.post("/webhooks/bank", json=payload)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


async def test_invalid_status_does_not_change_payment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    payment = await add_payment(db_session)

    response = await send(client, payment.id, "paid")

    assert response.status_code == 422
    assert await db_status(db_session, payment.id) is PaymentStatus.PENDING


# --- конкурентность: SELECT … FOR UPDATE ---


async def count_lock_waiters(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        result = await conn.scalar(
            text(
                "SELECT count(*) FROM pg_stat_activity"
                " WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
        )
        return int(result or 0)


async def send_while_row_locked(
    client: AsyncClient, engine: AsyncEngine, payment_id: uuid.UUID, statuses: list[str]
) -> list[Response]:
    """Держит строку платежа заблокированной, пока все вебхуки не встанут в ожидание.

    Так все запросы гарантированно конкурируют за одну строку, а не выполняются по очереди.
    """
    async with engine.connect() as conn, conn.begin():
        await conn.execute(select(Payment.id).where(Payment.id == payment_id).with_for_update())
        tasks = [asyncio.create_task(send(client, payment_id, s)) for s in statuses]
        for _ in range(500):
            if await count_lock_waiters(engine) >= len(statuses):
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("вебхуки не встали в ожидание блокировки")
    return list(await asyncio.gather(*tasks))


async def test_concurrent_same_webhook_applies_once(
    client: AsyncClient, db_session: AsyncSession, engine: AsyncEngine
) -> None:
    payment = await add_payment(db_session)

    responses = await send_while_row_locked(client, engine, payment.id, ["succeeded"] * 10)

    assert sorted(r.status_code for r in responses) == [200] + [409] * 9
    assert await db_status(db_session, payment.id) is PaymentStatus.SUCCEEDED


async def test_concurrent_conflicting_webhooks_one_wins(
    client: AsyncClient, db_session: AsyncSession, engine: AsyncEngine
) -> None:
    payment = await add_payment(db_session)
    statuses = ["succeeded", "failed"] * 5

    responses = await send_while_row_locked(client, engine, payment.id, statuses)

    winners = [s for s, r in zip(statuses, responses, strict=True) if r.status_code == 200]
    assert len(winners) == 1
    assert all(r.status_code in (200, 409) for r in responses)
    assert await db_status(db_session, payment.id) == winners[0]
