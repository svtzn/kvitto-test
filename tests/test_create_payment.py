import asyncio
import re
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentStatus

PRICES = {"basic": 990000, "standard": 1990000, "premium": 2990000}
RESPONSE_FIELDS = {
    "id",
    "status",
    "tariff_id",
    "amount",
    "discount",
    "method",
    "installment_months",
    "schedule",
    "email",
    "created_at",
}


def body(**overrides: Any) -> dict[str, Any]:
    return {"tariff_id": "standard", "email": "user@example.com", "method": "card"} | overrides


async def count_payments(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Payment)) or 0


async def get_payment(session: AsyncSession, payment_id: str) -> Payment:
    session.expire_all()
    return await session.get_one(Payment, uuid.UUID(payment_id))


# --- создание и формат ответа ---


async def test_create_card_payment(client: AsyncClient, db_session: AsyncSession) -> None:
    response = await client.post("/payments", json=body())

    assert response.status_code == 201
    data = response.json()
    assert set(data) == RESPONSE_FIELDS
    assert data["status"] == "pending"
    assert data["tariff_id"] == "standard"
    assert data["amount"] == 1990000
    assert data["discount"] == 0
    assert data["method"] == "card"
    assert data["installment_months"] is None
    assert data["schedule"] is None
    assert data["email"] == "user@example.com"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", data["created_at"])

    payment = await get_payment(db_session, data["id"])
    assert payment.status is PaymentStatus.PENDING
    assert (payment.amount, payment.discount) == (1990000, 0)
    assert payment.promo_code is None
    assert payment.idempotency_key is None
    assert await count_payments(db_session) == 1


async def test_create_sbp_payment(client: AsyncClient) -> None:
    response = await client.post("/payments", json=body(method="sbp", tariff_id="basic"))

    assert response.status_code == 201
    assert response.json()["amount"] == 990000


async def test_installment_months_null_for_card_is_absent(client: AsyncClient) -> None:
    response = await client.post("/payments", json=body(installment_months=None))

    assert response.status_code == 201
    assert response.json()["installment_months"] is None


# --- суммы и промокод (обязательный тест 1) ---


@pytest.mark.parametrize("tariff_id", list(PRICES))
async def test_amount_without_promo(
    client: AsyncClient, db_session: AsyncSession, tariff_id: str
) -> None:
    data = (await client.post("/payments", json=body(tariff_id=tariff_id))).json()

    assert data["discount"] == 0
    assert data["amount"] == PRICES[tariff_id]
    payment = await get_payment(db_session, data["id"])
    assert payment.amount == PRICES[tariff_id]


@pytest.mark.parametrize("promo", ["KVITTO10", "kvitto10", "  KvItTo10  "])
@pytest.mark.parametrize("tariff_id", list(PRICES))
async def test_amount_with_promo(
    client: AsyncClient, db_session: AsyncSession, tariff_id: str, promo: str
) -> None:
    response = await client.post("/payments", json=body(tariff_id=tariff_id, promo_code=promo))

    assert response.status_code == 201
    data = response.json()
    price = PRICES[tariff_id]
    assert data["discount"] == price // 10
    assert data["amount"] == price - price // 10
    payment = await get_payment(db_session, data["id"])
    assert (payment.amount, payment.discount) == (data["amount"], data["discount"])
    assert payment.promo_code == "KVITTO10"


@pytest.mark.parametrize("promo", ["", "   "])
async def test_empty_promo_is_absent(
    client: AsyncClient, db_session: AsyncSession, promo: str
) -> None:
    data = (await client.post("/payments", json=body(promo_code=promo))).json()

    assert (data["amount"], data["discount"]) == (1990000, 0)
    assert (await get_payment(db_session, data["id"])).promo_code is None


async def test_unknown_promo(client: AsyncClient, db_session: AsyncSession) -> None:
    response = await client.post("/payments", json=body(promo_code="NOPE"))

    assert response.status_code == 422
    assert response.json() == {"detail": "Unknown promo code"}
    assert await count_payments(db_session) == 0


# --- рассрочка (обязательный тест 2) ---


async def test_installment_example_from_requirements(client: AsyncClient) -> None:
    data = (
        await client.post("/payments", json=body(method="installment", installment_months=3))
    ).json()

    assert data["amount"] == 1990000
    assert data["installment_months"] == 3
    assert data["schedule"] == [663334, 663333, 663333]


@pytest.mark.parametrize("promo", [None, "kvitto10"])
@pytest.mark.parametrize("months", [3, 6, 12])
@pytest.mark.parametrize("tariff_id", list(PRICES))
async def test_installment_schedule(
    client: AsyncClient,
    db_session: AsyncSession,
    tariff_id: str,
    months: int,
    promo: str | None,
) -> None:
    response = await client.post(
        "/payments",
        json=body(
            tariff_id=tariff_id, method="installment", installment_months=months, promo_code=promo
        ),
    )

    assert response.status_code == 201
    data = response.json()
    schedule = data["schedule"]
    assert data["installment_months"] == months
    assert len(schedule) == months
    assert sum(schedule) == data["amount"]
    assert schedule == sorted(schedule, reverse=True)  # лишние копейки — в начале
    assert schedule[0] - schedule[-1] <= 1
    payment = await get_payment(db_session, data["id"])
    assert payment.schedule == schedule


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"method": "installment"}, id="installment-without-months"),
        pytest.param({"method": "installment", "installment_months": None}, id="months-null"),
        pytest.param({"method": "installment", "installment_months": 4}, id="months-4"),
        pytest.param({"method": "installment", "installment_months": 0}, id="months-0"),
        pytest.param({"method": "card", "installment_months": 3}, id="card-with-months"),
        pytest.param({"method": "sbp", "installment_months": 6}, id="sbp-with-months"),
    ],
)
async def test_invalid_installment(
    client: AsyncClient, db_session: AsyncSession, overrides: dict[str, Any]
) -> None:
    response = await client.post("/payments", json=body(**overrides))

    assert response.status_code == 422
    assert await count_payments(db_session) == 0


# --- прочая валидация ---


async def test_unknown_tariff(client: AsyncClient, db_session: AsyncSession) -> None:
    response = await client.post("/payments", json=body(tariff_id="gold"))

    assert response.status_code == 422
    assert response.json() == {"detail": "Unknown tariff"}
    assert await count_payments(db_session) == 0


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(body(email="not-an-email"), id="bad-email"),
        pytest.param(body(method="cash"), id="bad-method"),
        pytest.param({"email": "user@example.com", "method": "card"}, id="no-tariff"),
        pytest.param({"tariff_id": "basic", "method": "card"}, id="no-email"),
        pytest.param({"tariff_id": "basic", "email": "user@example.com"}, id="no-method"),
    ],
)
async def test_invalid_body(
    client: AsyncClient, db_session: AsyncSession, payload: dict[str, Any]
) -> None:
    response = await client.post("/payments", json=payload)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert await count_payments(db_session) == 0


# --- идемпотентность (обязательный тест 3) ---


async def test_same_idempotency_key_returns_same_payment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = {"Idempotency-Key": "key-1"}
    first = await client.post("/payments", json=body(), headers=headers)
    # тело повторного запроса не сравнивается
    second = await client.post("/payments", json=body(tariff_id="basic"), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert await count_payments(db_session) == 1
    payment = await get_payment(db_session, first.json()["id"])
    assert payment.idempotency_key == "key-1"


async def test_different_idempotency_keys_create_different_payments(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    first = await client.post("/payments", json=body(), headers={"Idempotency-Key": "a"})
    second = await client.post("/payments", json=body(), headers={"Idempotency-Key": "b"})

    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["id"] != second.json()["id"]
    assert await count_payments(db_session) == 2


@pytest.mark.parametrize("headers", [{}, {"Idempotency-Key": ""}, {"Idempotency-Key": "   "}])
async def test_without_key_each_request_creates_payment(
    client: AsyncClient, db_session: AsyncSession, headers: dict[str, str]
) -> None:
    first = await client.post("/payments", json=body(), headers=headers)
    second = await client.post("/payments", json=body(), headers=headers)

    assert (first.status_code, second.status_code) == (201, 201)
    assert await count_payments(db_session) == 2
    assert (await get_payment(db_session, first.json()["id"])).idempotency_key is None


async def test_idempotency_key_max_length(client: AsyncClient, db_session: AsyncSession) -> None:
    ok = await client.post("/payments", json=body(), headers={"Idempotency-Key": "k" * 255})
    too_long = await client.post("/payments", json=body(), headers={"Idempotency-Key": "k" * 256})

    assert ok.status_code == 201
    assert too_long.status_code == 422
    assert await count_payments(db_session) == 1


async def test_idempotency_key_concurrent_requests(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = {"Idempotency-Key": "race"}
    responses = await asyncio.gather(
        *(client.post("/payments", json=body(), headers=headers) for _ in range(10))
    )

    codes = sorted(r.status_code for r in responses)
    assert codes == [200] * 9 + [201]
    assert len({r.json()["id"] for r in responses}) == 1
    assert await count_payments(db_session) == 1
