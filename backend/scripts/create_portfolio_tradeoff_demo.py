"""Create and verify the deterministic local-vs-portfolio pitch batch."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.decision.actions import RecoveryAction  # noqa: E402
from app.models.recovery_batch import OptimizationAssignment  # noqa: E402
from app.schemas.optimization import OptimizationConstraintsRequest  # noqa: E402
from app.services.recovery_batch_service import (  # noqa: E402
    create_demo_batch,
    plan_batch,
)


REFERENCE_ID = "recoveriq-pitch-local-vs-portfolio-v1"
CONSTRAINTS = OptimizationConstraintsRequest(
    total_budget=2000,
    incentive_budget=1000,
    max_retries=350,
    max_contacts=300,
    max_whatsapp=150,
    max_incentive_actions=1,
    max_human_escalations=30,
    solver_timeout_ms=30000,
)


def _value(alternatives: list[dict], action: str) -> float:
    return float(next(item for item in alternatives if item["action"] == action)["incremental_value"])


def main() -> None:
    with SessionLocal() as db:
        batch = create_demo_batch(db, payment_count=20, reference_id=REFERENCE_ID)
        plan = plan_batch(db, batch.id, CONSTRAINTS)
        assignments = db.scalars(
            select(OptimizationAssignment)
            .where(OptimizationAssignment.plan_id == plan.id)
            .order_by(OptimizationAssignment.payment_id)
        ).all()

        incentive_receivers = [item for item in assignments if item.selected_action is RecoveryAction.INCENTIVE]
        targets = [
            item
            for item in assignments
            if item.standalone_best_action == RecoveryAction.INCENTIVE.value
            and item.selected_action is RecoveryAction.RETRY_LATER
            and item.selected_rank == 2
        ]
        if len(incentive_receivers) != 1 or not targets:
            raise RuntimeError("The real optimizer did not produce the required incentive tradeoff.")

        receiver = incentive_receivers[0]
        receiver_non_incentive = next(item for item in receiver.alternatives if item["action"] != "INCENTIVE")
        receiver_gain = _value(receiver.alternatives, "INCENTIVE") - float(receiver_non_incentive["incremental_value"])
        # The first deterministic fixture payment mirrors the original pitch
        # example and has a clear, non-trivial local incentive advantage.
        target = targets[0]
        target_gain = _value(target.alternatives, "INCENTIVE") - _value(target.alternatives, "RETRY_LATER")
        if receiver_gain <= target_gain:
            raise RuntimeError("The incentive receiver does not have the stronger marginal portfolio use.")

        print(f"BATCH_ID={batch.id}")
        print(f"TARGET_PAYMENT_ID={target.payment_id}")
        print(f"INCENTIVE_PAYMENT_ID={receiver.payment_id}")
        print(f"TARGET_INCENTIVE_VALUE={_value(target.alternatives, 'INCENTIVE'):.2f}")
        print(f"TARGET_RETRY_LATER_VALUE={_value(target.alternatives, 'RETRY_LATER'):.2f}")
        print(f"TARGET_INCENTIVE_MARGINAL_GAIN={target_gain:.2f}")
        print(f"RECEIVER_INCENTIVE_MARGINAL_GAIN={receiver_gain:.2f}")
        print("INCENTIVE_UTILIZATION=1/1")


if __name__ == "__main__":
    main()
