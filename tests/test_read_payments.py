import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
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


def ids(response_json: list[dict[str, Any]]) -> list[str]:
    return [p["id"] for p in response_json]


# --- GET /payments/{id} ---


async def test_get_payment_by_id(client: AsyncClient) -> None:
    created = await client.post(
        "/payments",
        json={
            "tariff_id": "premium",
            "email": "user@example.com",
            "method": "installment",
            "installment_months": 6,
            "promo_code": "kvitto10",
        },
    )

    response = await client.get(f"/payments/{created.json()['id']}")

    assert response.status_code == 200
    assert response.json() == created.json()


async def test_get_payment_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/payments/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Payment not found"}


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "123", "6f1c"])
async def test_get_payment_invalid_uuid(client: AsyncClient, bad_id: str) -> None:
    response = await client.get(f"/payments/{bad_id}")

    assert response.status_code == 422


# --- GET /payments ---


async def test_list_empty(client: AsyncClient) -> None:
    response = await client.get("/payments")

    assert response.status_code == 200
    assert response.json() == []


async def test_list_sorted_by_created_at_desc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    old = await add_payment(db_session, created_at=T0)
    new = await add_payment(db_session, created_at=T0 + timedelta(hours=2))
    mid = await add_payment(db_session, created_at=T0 + timedelta(hours=1))

    response = await client.get("/payments")

    assert response.status_code == 200
    assert ids(response.json()) == [str(new.id), str(mid.id), str(old.id)]


async def test_list_same_created_at_ordered_by_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    low = uuid.UUID("00000000-0000-4000-8000-000000000001")
    high = uuid.UUID("ffffffff-ffff-4fff-bfff-ffffffffffff")
    await add_payment(db_session, payment_id=low)
    await add_payment(db_session, payment_id=high)

    response = await client.get("/payments")

    assert ids(response.json()) == [str(high), str(low)]


async def test_list_response_format(client: AsyncClient) -> None:
    created = await client.post(
        "/payments",
        json={"tariff_id": "basic", "email": "user@example.com", "method": "card"},
        headers={"Idempotency-Key": "k"},
    )

    response = await client.get("/payments")

    assert response.json() == [created.json()]


@pytest.fixture
async def mixed_payments(db_session: AsyncSession) -> dict[str, Payment]:
    """Платежи двух пользователей в разных статусах."""
    rows = {
        "a_pending": ("alice@example.com", PaymentStatus.PENDING),
        "a_succeeded": ("alice@example.com", PaymentStatus.SUCCEEDED),
        "b_pending": ("bob@example.com", PaymentStatus.PENDING),
        "b_failed": ("bob@example.com", PaymentStatus.FAILED),
    }
    return {
        name: await add_payment(
            db_session, email=email, status=st, created_at=T0 + timedelta(minutes=i)
        )
        for i, (name, (email, st)) in enumerate(rows.items())
    }


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        pytest.param({}, ["b_failed", "b_pending", "a_succeeded", "a_pending"], id="no-filters"),
        pytest.param({"email": "alice@example.com"}, ["a_succeeded", "a_pending"], id="email"),
        pytest.param({"email": "ALICE@Example.com"}, ["a_succeeded", "a_pending"], id="email-ci"),
        pytest.param({"email": "carol@example.com"}, [], id="email-no-match"),
        pytest.param(
            {"email": ""}, ["b_failed", "b_pending", "a_succeeded", "a_pending"], id="email-empty"
        ),
        pytest.param({"status": "pending"}, ["b_pending", "a_pending"], id="status"),
        pytest.param({"status": "refunded"}, [], id="status-no-match"),
        pytest.param(
            {"email": "bob@example.com", "status": "pending"}, ["b_pending"], id="email-and-status"
        ),
        pytest.param({"email": "alice@example.com", "status": "failed"}, [], id="and-no-match"),
    ],
)
async def test_list_filters(
    client: AsyncClient,
    mixed_payments: dict[str, Payment],
    params: dict[str, str],
    expected: list[str],
) -> None:
    response = await client.get("/payments", params=params)

    assert response.status_code == 200
    assert ids(response.json()) == [str(mixed_payments[name].id) for name in expected]


@pytest.mark.parametrize("bad_status", ["unknown", "PENDING", ""])
async def test_list_unknown_status(client: AsyncClient, bad_status: str) -> None:
    response = await client.get("/payments", params={"status": bad_status})

    assert response.status_code == 422
