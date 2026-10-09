PROMO_CODES: dict[str, int] = {"KVITTO10": 10}


class UnknownPromoCode(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(f"Unknown promo code: {code!r}")
        self.code = code


def normalize_promo_code(code: str) -> str:
    return code.strip().upper()


def get_discount_percent(code: str) -> int:
    try:
        return PROMO_CODES[normalize_promo_code(code)]
    except KeyError:
        raise UnknownPromoCode(code) from None
