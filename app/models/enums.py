from enum import IntEnum, StrEnum


class PaymentMethod(StrEnum):
    CARD = "card"
    SBP = "sbp"
    INSTALLMENT = "installment"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class InstallmentMonths(IntEnum):
    THREE = 3
    SIX = 6
    TWELVE = 12
