import itertools

import pytest

from app.models import PaymentStatus
from app.services.transitions import can_transition

S = PaymentStatus
ALLOWED = {
    (S.PENDING, S.SUCCEEDED),
    (S.PENDING, S.FAILED),
    (S.SUCCEEDED, S.REFUNDED),
}


@pytest.mark.parametrize(("current", "new"), list(itertools.product(S, repeat=2)))
def test_can_transition(current: PaymentStatus, new: PaymentStatus) -> None:
    assert can_transition(current, new) is ((current, new) in ALLOWED)


@pytest.mark.parametrize("status", list(S))
def test_same_status_is_forbidden(status: PaymentStatus) -> None:
    assert not can_transition(status, status)


@pytest.mark.parametrize("status", [S.FAILED, S.REFUNDED])
def test_final_statuses_have_no_exits(status: PaymentStatus) -> None:
    assert not any(can_transition(status, new) for new in S)
