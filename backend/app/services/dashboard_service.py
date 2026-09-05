from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.decision.actions import RecoveryAction
from app.models.decision import RecoveryDecision
from app.models.enums import InterventionStatus, PaymentStatus
from app.models.intervention import Intervention
from app.models.outcome import Outcome
from app.models.payment import Payment
from app.schemas.dashboard import (
    DashboardOverviewResponse,
    InterventionMixItem,
    LivePortfolioSummary,
    OfflineEvaluationSummary,
    OfflineStrategyItem,
    RecentInterventionItem,
    RecentRecoveryItem,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
STRATEGY_ARTIFACT = PROJECT_ROOT / "data" / "processed" / "strategy_comparison.csv"
OFFLINE_LABEL = "OFFLINE / FROZEN TEST SET EVALUATION"


def _scalar_int(db: Session, statement) -> int:
    return int(db.scalar(statement) or 0)


def _scalar_decimal(db: Session, statement) -> Decimal:
    return Decimal(db.scalar(statement) or 0).quantize(Decimal("0.01"))


def _load_offline_evaluation() -> OfflineEvaluationSummary:
    if not STRATEGY_ARTIFACT.is_file():
        raise RuntimeError(
            f"Frozen strategy evaluation artifact is missing: {STRATEGY_ARTIFACT}"
        )

    rows: dict[str, dict[str, str]] = {}
    with STRATEGY_ARTIFACT.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows[row["strategy"]] = row

    required = ("BASELINE", "ML_DECISION", "OPTIMIZED")
    missing = [strategy for strategy in required if strategy not in rows]
    if missing:
        raise RuntimeError(
            "Frozen strategy evaluation artifact is malformed; missing: "
            + ", ".join(missing)
        )

    strategies = []
    for strategy in required:
        row = rows[strategy]
        strategies.append(
            OfflineStrategyItem(
                strategy=strategy,
                payments=int(row["payments"]),
                net_value=Decimal(row["expected_net_revenue"]).quantize(
                    Decimal("0.01")
                ),
                recovery_rate=round(
                    float(row["expected_recovery_rate"]) * 100,
                    2,
                ),
                uplift_amount=Decimal(
                    row["additional_net_revenue_vs_baseline"]
                ).quantize(Decimal("0.01")),
                uplift_percent=round(
                    float(row["net_uplift_percent_vs_baseline"]),
                    2,
                ),
            )
        )

    return OfflineEvaluationSummary(
        label=OFFLINE_LABEL,
        solver_status="OPTIMAL",
        strategies=strategies,
    )


def get_dashboard_overview(db: Session) -> DashboardOverviewResponse:
    failed_payments = _scalar_int(
        db,
        select(func.count(Payment.id)).where(Payment.status == PaymentStatus.FAILED),
    )
    recovered_payments = _scalar_int(
        db,
        select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.RECOVERED
        ),
    )
    resolved_population = failed_payments + recovered_payments

    portfolio = LivePortfolioSummary(
        failed_payments=failed_payments,
        recovered_payments=recovered_payments,
        revenue_at_risk=_scalar_decimal(
            db,
            select(func.sum(Payment.amount)).where(
                Payment.status == PaymentStatus.FAILED
            ),
        ),
        recovered_revenue=_scalar_decimal(
            db,
            select(func.sum(Outcome.recovered_amount)).where(
                Outcome.recovered.is_(True)
            ),
        ),
        recovery_rate=(
            recovered_payments / resolved_population * 100
            if resolved_population
            else 0.0
        ),
        active_interventions=_scalar_int(
            db,
            select(func.count(Intervention.id)).where(
                Intervention.status.in_(
                    [InterventionStatus.PLANNED, InterventionStatus.EXECUTED]
                )
            ),
        ),
        recorded_expected_value=_scalar_decimal(
            db,
            select(func.sum(RecoveryDecision.expected_value)),
        ),
    )

    counts = dict(
        db.execute(
            select(Intervention.action_type, func.count(Intervention.id)).group_by(
                Intervention.action_type
            )
        ).all()
    )
    intervention_mix = [
        InterventionMixItem(action=action.value, count=int(counts.get(action, 0)))
        for action in RecoveryAction
    ]

    intervention_rows = db.execute(
        select(Intervention, RecoveryDecision)
        .join(RecoveryDecision, Intervention.decision_id == RecoveryDecision.id)
        .order_by(Intervention.created_at.desc(), Intervention.id.desc())
        .limit(6)
    ).all()
    recent_interventions = [
        RecentInterventionItem(
            intervention_id=intervention.id,
            payment_id=decision.payment_id,
            action=intervention.action_type.value,
            status=intervention.status.value,
            provider=intervention.provider,
            provider_status=intervention.provider_status,
            expected_value=decision.expected_value,
            created_at=intervention.created_at,
        )
        for intervention, decision in intervention_rows
    ]

    recovery_rows = db.execute(
        select(Outcome, Intervention, RecoveryDecision)
        .join(Intervention, Outcome.intervention_id == Intervention.id)
        .join(RecoveryDecision, Intervention.decision_id == RecoveryDecision.id)
        .where(Outcome.recovered.is_(True))
        .order_by(Outcome.completed_at.desc(), Outcome.id.desc())
        .limit(6)
    ).all()
    recent_recoveries = [
        RecentRecoveryItem(
            payment_id=decision.payment_id,
            recovered_amount=outcome.recovered_amount,
            action=intervention.action_type.value,
            provider=intervention.provider,
            completed_at=outcome.completed_at,
        )
        for outcome, intervention, decision in recovery_rows
    ]

    return DashboardOverviewResponse(
        portfolio=portfolio,
        intervention_mix=intervention_mix,
        recent_interventions=recent_interventions,
        recent_recoveries=recent_recoveries,
        offline_evaluation=_load_offline_evaluation(),
    )
