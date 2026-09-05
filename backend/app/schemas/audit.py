from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class AuditEvent(BaseModel):
    event_type: str
    title: str
    status: str | None
    timestamp: datetime | None
    # Audit evidence includes nested, persisted JSON such as candidate rankings,
    # policy evidence, and the portfolio constraint snapshot.
    details: dict[str, Any]


class PaymentAuditResponse(BaseModel):
    payment_id: int
    amount: Decimal
    currency: str
    payment_method: str
    current_status: str
    source: str = "LIVE_SYSTEM_DATABASE"
    events: list[AuditEvent]
