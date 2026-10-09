PROMO_CODES: dict[str, int] = {"KVITTO10": 10}


class UnknownPromoCode(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(f"Unknown promo code: {code!r}")
        self.code = code


def get_discount_percent(code: str) -> int:
    try:
        return PROMO_CODES[code.strip().upper()]
    except KeyError:
        raise UnknownPromoCode(code) from None
