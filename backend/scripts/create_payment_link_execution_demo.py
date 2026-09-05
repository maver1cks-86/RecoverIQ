"""Create a fresh, unexecuted Razorpay Payment Link recording fixture."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.decision.actions import RecoveryAction  # noqa: E402
from app.models.enums import PaymentStatus, PolicyStatus  # noqa: E402
from app.models.outcome import Outcome  # noqa: E402
from app.models.recovery_batch import OptimizationAssignment  # noqa: E402
from app.schemas.optimization import OptimizationConstraintsRequest  # noqa: E402
from app.services.recovery_batch_service import (  # noqa: E402
    batch_summary,
    create_demo_batch,
    plan_batch,
)


CONSTRAINTS = OptimizationConstraintsRequest(
    total_budget=2000,
    incentive_budget=0,
    max_retries=0,
    max_contacts=1,
    max_whatsapp=0,
    max_incentive_actions=0,
    max_human_escalations=0,
    solver_timeout_ms=30000,
    enabled_actions=[RecoveryAction.PAYMENT_LINK, RecoveryAction.DO_NOTHING],
)


def main() -> None:
    reference = f"recoveriq-live-payment-link-{uuid4().hex}"
    with SessionLocal() as db:
        batch = create_demo_batch(db, payment_count=20, reference_id=reference)
        plan = plan_batch(db, batch.id, CONSTRAINTS)
        assignments = db.scalars(
            select(OptimizationAssignment)
            .where(OptimizationAssignment.plan_id == plan.id)
            .order_by(OptimizationAssignment.payment_id)
        ).all()
        links = [item for item in assignments if item.selected_action is RecoveryAction.PAYMENT_LINK]
        if len(links) != 1:
            raise RuntimeError(f"Expected exactly one PAYMENT_LINK assignment, found {len(links)}.")

        target = links[0]
        if (
            target.payment.status is not PaymentStatus.FAILED
            or target.policy_status is not PolicyStatus.ALLOWED
            or target.incremental_value <= 0
            or target.execution_status != "PLANNED"
            or target.intervention_id is not None
            or target.provider_action_id is not None
            or db.scalar(select(Outcome).where(Outcome.intervention_id == target.intervention_id)) is not None
        ):
            raise RuntimeError("The generated target is not clean and execution-ready.")

        summary = batch_summary(db, batch.id)
        if summary["observed_recovered_amount"] != 0:
            raise RuntimeError("The fresh recording batch unexpectedly contains a recovered outcome.")

        print(f"BATCH_ID={batch.id}")
        print(f"TARGET_PAYMENT_ID={target.payment_id}")
        print(f"TARGET_AMOUNT={target.payment.amount}")
        print(f"TARGET_INCREMENTAL_VALUE={target.incremental_value}")
        print(f"TARGET_RANK={target.selected_rank}")
        print(f"ACTION_ALLOCATION={summary['action_allocation']}")
        print("TARGET_STATUS=FAILED/PLANNED")
        print("OBSERVED_RECOVERED_AMOUNT=0.00")


if __name__ == "__main__":
    main()
