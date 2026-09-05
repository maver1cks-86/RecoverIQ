from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class LivePortfolioSummary(BaseModel):
    failed_payments: int
    recovered_payments: int
    revenue_at_risk: Decimal
    recovered_revenue: Decimal
    recovery_rate: float
    active_interventions: int
    recorded_expected_value: Decimal


class InterventionMixItem(BaseModel):
    action: str
    count: int


class RecentInterventionItem(BaseModel):
    intervention_id: int
    payment_id: int
    action: str
    status: str
    provider: str | None
    provider_status: str | None
    expected_value: Decimal
    created_at: datetime


class RecentRecoveryItem(BaseModel):
    payment_id: int
    recovered_amount: Decimal
    action: str
    provider: str | None
    completed_at: datetime | None


class OfflineStrategyItem(BaseModel):
    strategy: str
    payments: int
    net_value: Decimal
    recovery_rate: float
    uplift_amount: Decimal
    uplift_percent: float


class OfflineEvaluationSummary(BaseModel):
    label: str
    solver_status: str
    strategies: list[OfflineStrategyItem]


class DashboardOverviewResponse(BaseModel):
    portfolio: LivePortfolioSummary
    intervention_mix: list[InterventionMixItem]
    recent_interventions: list[RecentInterventionItem]
    recent_recoveries: list[RecentRecoveryItem]
    offline_evaluation: OfflineEvaluationSummary
