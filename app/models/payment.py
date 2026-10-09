import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import PaymentMethod, PaymentStatus


def _str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    # VARCHAR + CHECK вместо нативного ENUM Postgres: проще менять набор значений миграцией
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda cls: [m.value for m in cls],
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint("discount >= 0", name="discount_non_negative"),
        CheckConstraint(
            # явные IS NOT NULL: CHECK, вычисленный в NULL, считается пройденным
            "(method = 'installment'"
            " AND installment_months IS NOT NULL AND schedule IS NOT NULL"
            " AND installment_months IN (3, 6, 12)"
            " AND cardinality(schedule) = installment_months)"
            " OR (method <> 'installment'"
            " AND installment_months IS NULL AND schedule IS NULL)",
            name="installment_consistency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    status: Mapped[PaymentStatus] = mapped_column(
        _str_enum(PaymentStatus, "payment_status"), default=PaymentStatus.PENDING
    )
    tariff_id: Mapped[str] = mapped_column(String(32), ForeignKey("tariffs.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    discount: Mapped[int] = mapped_column(BigInteger)
    method: Mapped[PaymentMethod] = mapped_column(_str_enum(PaymentMethod, "payment_method"))
    installment_months: Mapped[int | None] = mapped_column(Integer)
    schedule: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger))
    email: Mapped[str] = mapped_column(String(320), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    promo_code: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True)
