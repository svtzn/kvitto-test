from dataclasses import dataclass


@dataclass(frozen=True)
class PriceBreakdown:
    discount: int
    amount: int
    schedule: list[int] | None


def calc_discount(price: int, percent: int) -> int:
    """Скидка в копейках, округление вниз."""
    return price * percent // 100


def build_schedule(amount: int, months: int) -> list[int]:
    """График рассрочки в копейках; лишние копейки уходят в первые платежи."""
    if months <= 0:
        raise ValueError(f"months must be positive, got {months}")
    base, rest = divmod(amount, months)
    return [base + 1] * rest + [base] * (months - rest)


def calc_price(price: int, discount_percent: int, months: int | None) -> PriceBreakdown:
    """Скидка, сумма к оплате и график (если задано число месяцев рассрочки)."""
    discount = calc_discount(price, discount_percent)
    amount = price - discount
    schedule = build_schedule(amount, months) if months is not None else None
    return PriceBreakdown(discount=discount, amount=amount, schedule=schedule)
