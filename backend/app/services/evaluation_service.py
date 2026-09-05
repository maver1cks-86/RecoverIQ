from __future__ import annotations

import csv
from pathlib import Path

from app.schemas.evaluation import (
    BaselineEvaluation,
    EvaluationAssignment,
    EvaluationAssignmentPage,
    EvaluationConstraints,
    EvaluationDataset,
    EvaluationSummary,
    RecoverIQEvaluation,
    ScaleBenchmark,
    UnconstrainedEvaluation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
STRATEGY_COMPARISON = PROJECT_ROOT / "data" / "processed" / "strategy_comparison.csv"
STRATEGY_ASSIGNMENTS = PROJECT_ROOT / "data" / "processed" / "strategy_assignments.csv"

# Frozen measured local planning benchmark. This is intentionally immutable and
# is not derived from database state or rerun when the endpoint is requested.
SCALE_BENCHMARKS = (
    ScaleBenchmark(payments=1000, feature_prep_seconds=0.4538, ml_scoring_seconds=0.3972, policy_economics_seconds=0.2263, solver_seconds=11.8103, total_seconds=12.8876, status="OPTIMAL"),
    ScaleBenchmark(payments=5000, feature_prep_seconds=2.2967, ml_scoring_seconds=1.4428, policy_economics_seconds=1.3017, solver_seconds=22.3529, total_seconds=27.3940, status="OPTIMAL"),
    ScaleBenchmark(payments=10000, feature_prep_seconds=2.7313, ml_scoring_seconds=2.9610, policy_economics_seconds=3.1464, solver_seconds=39.4630, total_seconds=48.3018, status="FEASIBLE"),
)


def _comparison_rows() -> dict[str, dict[str, str]]:
    if not STRATEGY_COMPARISON.is_file():
        raise RuntimeError(f"Frozen evaluation artifact is missing: {STRATEGY_COMPARISON}")
    with STRATEGY_COMPARISON.open(encoding="utf-8", newline="") as handle:
        rows = {row["strategy"]: row for row in csv.DictReader(handle)}
    missing = {"BASELINE", "ML_DECISION", "OPTIMIZED"} - rows.keys()
    if missing:
        raise RuntimeError(f"Frozen evaluation artifact is missing strategies: {sorted(missing)}")
    return rows


def get_evaluation_summary() -> EvaluationSummary:
    rows = _comparison_rows()
    baseline, ml, optimized = rows["BASELINE"], rows["ML_DECISION"], rows["OPTIMIZED"]
    return EvaluationSummary(
        evaluation_name="RecoverIQ Phase 17 Frozen Offline Evaluation",
        dataset=EvaluationDataset(type="synthetic", role="frozen_held_out_test", total_records=50000, train_records=32000, validation_records=8000, test_records=10000),
        baseline=BaselineEvaluation(net_recovery=round(float(baseline["expected_net_revenue"]), 2), recovery_rate=round(float(baseline["expected_recovery_rate"]), 4)),
        unconstrained_ml=UnconstrainedEvaluation(net_recovery=round(float(ml["expected_net_revenue"]), 2), improvement=round(float(ml["additional_net_revenue_vs_baseline"]), 2), relative_improvement_percent=round(float(ml["net_uplift_percent_vs_baseline"]), 2), constraint_status="UNCONSTRAINED_BENCHMARK"),
        recoveriq=RecoverIQEvaluation(net_recovery=round(float(optimized["expected_net_revenue"]), 2), improvement=round(float(optimized["additional_net_revenue_vs_baseline"]), 2), relative_improvement_percent=round(float(optimized["net_uplift_percent_vs_baseline"]), 2), recovery_rate=round(float(optimized["expected_recovery_rate"]), 4), solver_status="OPTIMAL"),
        constraints=EvaluationConstraints(total_recovery_spend=20000, incentive_budget=10000, retry_capacity=3500, contact_capacity=3000, whatsapp_capacity=1500, max_incentive_actions=500, max_human_escalations=300, solver_timeout_ms=120000),
        scale_benchmarks=list(SCALE_BENCHMARKS),
    )


def get_evaluation_assignments(page: int, page_size: int, search: str | None = None, action: str | None = None, strategy: str | None = None) -> EvaluationAssignmentPage:
    if not STRATEGY_ASSIGNMENTS.is_file():
        raise RuntimeError(f"Frozen assignment artifact is missing: {STRATEGY_ASSIGNMENTS}")
    with STRATEGY_ASSIGNMENTS.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = [row for row in reader if (not search or search.lower() in row["payment_id"].lower()) and (not action or row["action"] == action) and (not strategy or row["strategy"] == strategy)]
    start = (page - 1) * page_size
    items = [EvaluationAssignment(payment_id=row["payment_id"], strategy=row["strategy"], action=row["action"], amount=float(row["amount"]), true_recovery_probability=float(row["true_recovery_probability"]), expected_gross_revenue=float(row["expected_gross_revenue"]), expected_net_revenue=float(row["expected_net_revenue"]), intervention_cost=float(row["intervention_cost"]), incentive_cost=float(row["incentive_cost"])) for row in rows[start:start + page_size]]
    return EvaluationAssignmentPage(artifact=STRATEGY_ASSIGNMENTS.name, columns=columns, items=items, page=page, page_size=page_size, total=len(rows))

