import pytest

from app.models import InstallmentMonths
from app.services.pricing import build_schedule, calc_discount

TARIFF_PRICES = [990000, 1990000, 2990000]


@pytest.mark.parametrize(
    ("price", "percent", "expected"),
    [
        (1990000, 0, 0),
        (1990000, 10, 199000),
        (990000, 10, 99000),
        (2990000, 10, 299000),
        (999, 10, 99),  # 99.9 → 99: округление вниз
        (1, 10, 0),
        (1990000, 100, 1990000),
    ],
)
def test_calc_discount(price: int, percent: int, expected: int) -> None:
    assert calc_discount(price, percent) == expected


def test_schedule_example_from_requirements() -> None:
    assert build_schedule(1990000, 3) == [663334, 663333, 663333]


@pytest.mark.parametrize("months", list(InstallmentMonths))
@pytest.mark.parametrize(
    "amount",
    [*TARIFF_PRICES, *(p - calc_discount(p, 10) for p in TARIFF_PRICES), 1, 0, 1000001],
)
def test_schedule_invariants(amount: int, months: int) -> None:
    schedule = build_schedule(amount, months)

    assert len(schedule) == months
    assert sum(schedule) == amount
    # лишние копейки — в начале: платежи не возрастают и отличаются не больше чем на 1
    assert schedule == sorted(schedule, reverse=True)
    assert schedule[0] - schedule[-1] <= 1


@pytest.mark.parametrize(
    ("amount", "months", "expected"),
    [
        (100, 3, [34, 33, 33]),
        (101, 3, [34, 34, 33]),
        (102, 3, [34, 34, 34]),
        (17, 12, [2, 2, 2, 2, 2, 1, 1, 1, 1, 1, 1, 1]),
    ],
)
def test_schedule_extra_kopecks_go_first(amount: int, months: int, expected: list[int]) -> None:
    assert build_schedule(amount, months) == expected


@pytest.mark.parametrize("months", [0, -3])
def test_schedule_rejects_non_positive_months(months: int) -> None:
    with pytest.raises(ValueError):
        build_schedule(100, months)
