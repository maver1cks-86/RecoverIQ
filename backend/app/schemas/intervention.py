from datetime import datetime

from pydantic import BaseModel


class InterventionListItem(BaseModel):
    intervention_id: int
    payment_id: int
    action: str
    provider: str | None
    provider_action_id: str | None
    provider_status: str | None
    status: str
    executed_at: datetime | None
    created_at: datetime


class InterventionListResponse(BaseModel):
    items: list[InterventionListItem]
    page: int
    page_size: int
    total: int
