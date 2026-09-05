"""Inspect persisted Phase 27.5 portfolio-decision evidence without rescoring."""
from __future__ import annotations

import argparse
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.models.recovery_batch import OptimizationAssignment, OptimizationPlan, RecoveryBatch


def _money(value: object) -> str:
    return f"INR {Decimal(str(value)):,.2f}"


def _print_assignment(label: str, item: OptimizationAssignment) -> None:
    alternatives = item.alternatives or []
    standalone = next((row for row in alternatives if row.get("rank") == 1), None)
    gap = Decimal(str((standalone or {}).get("incremental_value", item.incremental_value))) - item.incremental_value
    print(f"\n{label}")
    print(f"  payment_id: {item.payment_id}")
    print(f"  amount: {_money(item.payment.amount)}")
    print(f"  selected_action: {item.selected_action.value}")
    print(f"  standalone_best: {item.standalone_best_action}")
    print(f"  selected_rank: {item.selected_rank}")
    print(f"  selected_incremental_value: {_money(item.incremental_value)}")
    print(f"  standalone_incremental_value: {_money((standalone or {}).get('incremental_value', item.incremental_value))}")
    print(f"  value_gap: {_money(gap)}")
    print(f"  policy_status: {item.policy_status.value}")
    print(f"  portfolio_agreement: {item.portfolio_agreement}")
    print(f"  execution_status: {item.execution_status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a persisted recovery batch plan.")
    parser.add_argument("batch_id", type=int)
    args = parser.parse_args()
    with SessionLocal() as db:
        batch = db.get(RecoveryBatch, args.batch_id)
        if batch is None:
            raise SystemExit(f"RecoveryBatch {args.batch_id} was not found.")
        plan = db.scalar(select(OptimizationPlan).where(OptimizationPlan.batch_id == batch.id).order_by(OptimizationPlan.id.desc()))
        if plan is None:
            raise SystemExit(f"RecoveryBatch {args.batch_id} has no persisted plan.")
        items = list(db.scalars(select(OptimizationAssignment).options(joinedload(OptimizationAssignment.payment)).where(OptimizationAssignment.plan_id == plan.id).order_by(OptimizationAssignment.id)))
        print(f"Batch {batch.id} | {batch.payment_count} payments | risk {_money(batch.revenue_at_risk)} | solver {plan.solver_status}")
        print(f"Constraints: {plan.constraints_snapshot}")
        agreement = next((item for item in items if item.portfolio_agreement is True), None)
        disagreement = next((item for item in items if item.portfolio_agreement is False), None)
        no_action = next((item for item in items if item.selected_action.value == "DO_NOTHING" or item.execution_status == "NO_ACTION"), None)
        if agreement: _print_assignment("A. Standalone best == portfolio selected", agreement)
        else: print("\nA. No agreement example found in this plan.")
        if disagreement: _print_assignment("B. Portfolio constraints changed the local assignment", disagreement)
        else: print("\nB. No disagreement example found in this plan.")
        if no_action: _print_assignment("C. DO_NOTHING / NO_ACTION", no_action)
        else:
            lowest = min(items, key=lambda item: item.incremental_value)
            _print_assignment("C. Lowest-value selected assignment (no DO_NOTHING found)", lowest)


if __name__ == "__main__":
    main()
