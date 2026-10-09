def calc_discount(price: int, percent: int) -> int:
    """Скидка в копейках, округление вниз."""
    return price * percent // 100


def build_schedule(amount: int, months: int) -> list[int]:
    """График рассрочки в копейках; лишние копейки уходят в первые платежи."""
    if months <= 0:
        raise ValueError(f"months must be positive, got {months}")
    base, rest = divmod(amount, months)
    return [base + 1] * rest + [base] * (months - rest)
