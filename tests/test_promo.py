import pytest

from app.promo import UnknownPromoCode, get_discount_percent


@pytest.mark.parametrize(
    "code", ["KVITTO10", "kvitto10", "KvItTo10", "  kvitto10  ", "\tKVITTO10\n"]
)
def test_known_code_case_and_space_insensitive(code: str) -> None:
    assert get_discount_percent(code) == 10


@pytest.mark.parametrize("code", ["NOPE", "KVITTO 10", "KVITTO1", ""])
def test_unknown_code_raises(code: str) -> None:
    with pytest.raises(UnknownPromoCode) as exc_info:
        get_discount_percent(code)

    assert exc_info.value.code == code
