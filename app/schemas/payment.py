import uuid
from datetime import UTC, datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, EmailStr, field_serializer, model_validator

from app.models import InstallmentMonths, PaymentMethod, PaymentStatus
from app.schemas.common import BlankToNone


class PaymentCreate(BaseModel):
    tariff_id: str
    email: EmailStr
    method: PaymentMethod
    installment_months: InstallmentMonths | None = None
    promo_code: Annotated[str | None, BlankToNone] = None

    @model_validator(mode="after")
    def check_installment_months(self) -> Self:
        if self.method is PaymentMethod.INSTALLMENT and self.installment_months is None:
            raise ValueError("installment_months is required for installment")
        if self.method is not PaymentMethod.INSTALLMENT and self.installment_months is not None:
            raise ValueError("installment_months is allowed only for installment")
        return self


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: PaymentStatus
    tariff_id: str
    amount: int
    discount: int
    method: PaymentMethod
    installment_months: int | None
    schedule: list[int] | None
    email: str
    created_at: datetime

    @field_serializer("created_at")
    def created_at_to_seconds(self, value: datetime) -> datetime:
        # формат ответа: UTC с точностью до секунд, "2026-10-09T13:04:00Z"
        return value.astimezone(UTC).replace(microsecond=0)
