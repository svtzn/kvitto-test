import uuid
from typing import Literal

from pydantic import BaseModel

from app.models import PaymentStatus


class BankWebhook(BaseModel):
    payment_id: uuid.UUID
    status: PaymentStatus


class WebhookResult(BaseModel):
    result: Literal["ok"] = "ok"


class WebhookError(BaseModel):
    error: Literal["invalid_transition"] = "invalid_transition"
