from decimal import Decimal
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.database import SessionLocal
from app.decision.actions import RecoveryAction
from app.main import app
from app.models.customer import Customer
from app.models.decision import RecoveryDecision
from app.models.enums import PaymentStatus, PolicyStatus
from app.models.intervention import Intervention
from app.models.merchant import Merchant
from app.models.outcome import Outcome
from app.models.payment import Payment
from app.models.recovery_batch import OptimizationAssignment, OptimizationPlan, RecoveryBatch, RecoveryBatchPayment
from app.models.webhook_event import WebhookEvent
from app.schemas.optimization import OptimizationConstraintsRequest
from app.services.recovery_batch_service import create_demo_batch, plan_batch
from app.services.recovery_service import RecoveryExecutionResult
from app.services.revenue_risk_service import RevenueRiskService
from app.tasks.batch_tasks import execute_recovery_assignment_task

client = TestClient(app)


def cleanup() -> None:
    with SessionLocal() as db:
        for model in [WebhookEvent, Outcome, OptimizationAssignment, OptimizationPlan, RecoveryBatchPayment, RecoveryBatch, Intervention, RecoveryDecision, Payment, Customer, Merchant]: db.execute(delete(model))
        db.commit()


def planned_batch(count: int = 6) -> tuple[int, int]:
    with SessionLocal() as db:
        batch = create_demo_batch(db, count)
        plan = plan_batch(db, batch.id, OptimizationConstraintsRequest(total_budget=10, max_retries=1, max_contacts=1, max_whatsapp=0, max_incentive_actions=0, max_human_escalations=0))
        return batch.id, plan.id


def test_revenue_risk_is_explicit_and_deterministic() -> None:
    payment = Payment(amount=Decimal("10"), status=PaymentStatus.FAILED)
    assert RevenueRiskService.is_at_risk(payment)
    payment.status = PaymentStatus.RECOVERED
    assert not RevenueRiskService.is_at_risk(payment)
    assert RevenueRiskService.amount_at_risk(payment) == Decimal("0.00")


def test_demo_ingestion_is_idempotent_for_reference() -> None:
    cleanup()
    try:
        first = client.post("/recovery-batches/demo", json={"payment_count": 4, "reference_id": "batch-idempotency-test"})
        second = client.post("/recovery-batches/demo", json={"payment_count": 4, "reference_id": "batch-idempotency-test"})
        assert first.json()["id"] == second.json()["id"]
        with SessionLocal() as db:
            assert db.query(Payment).count() == 4
    finally: cleanup()


def test_demo_batch_creation_has_no_planning_or_execution_side_effects() -> None:
    cleanup()
    try:
        with SessionLocal() as db:
            batch = create_demo_batch(db, 5, reference_id="batch-creation-boundary")
            payment_ids = db.scalars(
                select(RecoveryBatchPayment.payment_id).where(
                    RecoveryBatchPayment.batch_id == batch.id
                )
            ).all()

            assert batch.source == "DEMO_SYNTHETIC_FAILED_PAYMENTS"
            assert batch.payment_count == 5
            assert len(payment_ids) == 5
            assert batch.revenue_at_risk > 0
            assert db.scalar(
                select(func.count(Payment.id)).where(
                    Payment.id.in_(payment_ids),
                    Payment.status == PaymentStatus.FAILED,
                )
            ) == 5
            assert db.scalar(
                select(func.count(OptimizationPlan.id)).where(
                    OptimizationPlan.batch_id == batch.id
                )
            ) == 0
            assert db.scalar(select(func.count(Intervention.id))) == 0

            summary = client.get(f"/recovery-batches/{batch.id}/summary").json()
            assert summary["estimated_incremental_value"] == "0.00"
            assert summary["observed_recovered_amount"] == "0.00"
    finally:
        cleanup()


def test_plan_and_assignments_are_durable_and_paginated() -> None:
    cleanup()
    try:
        batch_id, plan_id = planned_batch(7)
        with SessionLocal() as restarted:
            assert restarted.get(RecoveryBatch, batch_id).status == "READY"
            assert restarted.get(OptimizationPlan, plan_id).solver_status in {"OPTIMAL", "FEASIBLE"}
            assert restarted.query(OptimizationAssignment).filter_by(plan_id=plan_id).count() == 7
        page = client.get(f"/recovery-batches/{batch_id}/assignments?page=1&page_size=3").json()
        assert page["total"] == 7 and len(page["items"]) == 3
        assert page["items"][0]["standalone_best_action"]
        assert page["items"][0]["selected_rank"] >= 1
        assert len(page["items"][0]["alternatives"]) >= 1
        summary = client.get(f"/recovery-batches/{batch_id}/summary").json()
        assert summary["observed_recovered_amount"] == "0.00"
        assert Decimal(summary["estimated_incremental_value"]) >= 0
        assert all(item["used"] <= item["limit"] + 1e-6 for item in summary["constraint_utilization"])
        assert summary["constraints_snapshot"]["total_budget"] == 10.0
    finally: cleanup()


def test_replanning_changed_constraints_creates_new_version_and_rank_tradeoff() -> None:
    cleanup()
    try:
        with SessionLocal() as db:
            batch = create_demo_batch(db, 6)
            loose = plan_batch(
                db,
                batch.id,
                OptimizationConstraintsRequest(
                    total_budget=5000,
                    incentive_budget=5000,
                    max_incentive_actions=6,
                ),
            )
            batch.status = "QUEUED"
            db.commit()
            replay = plan_batch(
                db,
                batch.id,
                OptimizationConstraintsRequest(
                    total_budget=5000,
                    incentive_budget=5000,
                    max_incentive_actions=6,
                ),
            )
            assert replay.id == loose.id
            assert db.get(RecoveryBatch, batch.id).status == "READY"
            tight = plan_batch(
                db,
                batch.id,
                OptimizationConstraintsRequest(
                    total_budget=5000,
                    incentive_budget=5000,
                    max_incentive_actions=0,
                ),
            )
            assert tight.id != loose.id
            assert (loose.version, tight.version) == (1, 2)
            assert tight.constraints_snapshot["max_incentive_actions"] == 0
            assignments = db.scalars(
                select(OptimizationAssignment).where(
                    OptimizationAssignment.plan_id == tight.id
                )
            ).all()
            assert all(item.selected_action is not RecoveryAction.INCENTIVE for item in assignments)
            assert any(item.selected_rank > 1 for item in assignments)
    finally:
        cleanup()


def test_pitch_fixture_produces_real_incentive_capacity_tradeoff() -> None:
    cleanup()
    try:
        with SessionLocal() as db:
            batch = create_demo_batch(db, 20, reference_id="pitch-tradeoff-regression")
            plan = plan_batch(
                db,
                batch.id,
                OptimizationConstraintsRequest(max_incentive_actions=1),
            )
            assignments = db.scalars(
                select(OptimizationAssignment)
                .where(OptimizationAssignment.plan_id == plan.id)
                .order_by(OptimizationAssignment.payment_id)
            ).all()
            incentives = [item for item in assignments if item.selected_action is RecoveryAction.INCENTIVE]
            targets = [
                item for item in assignments
                if item.standalone_best_action == RecoveryAction.INCENTIVE.value
                and item.selected_action is RecoveryAction.RETRY_LATER
                and item.selected_rank == 2
            ]
            assert len(incentives) == 1
            assert targets
            assert plan.constraints_snapshot["max_incentive_actions"] == 1
            usage = next(item for item in plan.resource_usage if item["key"] == "incentives")
            assert usage == {"key": "incentives", "used": 1, "limit": 1}

            target = targets[0]
            receiver = incentives[0]
            target_values = {item["action"]: item["incremental_value"] for item in target.alternatives}
            receiver_fallback = next(item for item in receiver.alternatives if item["action"] != "INCENTIVE")
            receiver_gain = next(item for item in receiver.alternatives if item["action"] == "INCENTIVE")["incremental_value"] - receiver_fallback["incremental_value"]
            target_gain = target_values["INCENTIVE"] - target_values["RETRY_LATER"]
            assert receiver_gain > target_gain

        with patch("app.services.llm_provider.GroundedLLMProvider.explain", return_value=None):
            response = client.post(
                "/copilot/chat",
                json={
                    "message": "Why was rank 2 RETRY_LATER selected instead of rank 1 INCENTIVE?",
                    "context": {"payment_id": target.payment_id},
                },
            )
        assert response.status_code == 200
        assert "max_incentive_actions = 1" in response.json()["answer"]
        assert f"Payment #{receiver.payment_id}" in response.json()["answer"]
    finally:
        cleanup()


def test_live_execution_constraints_select_one_clean_payment_link() -> None:
    cleanup()
    try:
        with SessionLocal() as db:
            batch = create_demo_batch(db, 20, reference_id="payment-link-demo-regression")
            plan = plan_batch(
                db,
                batch.id,
                OptimizationConstraintsRequest(
                    total_budget=2000,
                    incentive_budget=0,
                    max_retries=0,
                    max_contacts=1,
                    max_whatsapp=0,
                    max_incentive_actions=0,
                    max_human_escalations=0,
                    enabled_actions=[RecoveryAction.PAYMENT_LINK, RecoveryAction.DO_NOTHING],
                ),
            )
            assignments = db.scalars(
                select(OptimizationAssignment).where(OptimizationAssignment.plan_id == plan.id)
            ).all()
            links = [item for item in assignments if item.selected_action is RecoveryAction.PAYMENT_LINK]
            assert len(links) == 1
            target = links[0]
            assert target.payment.status is PaymentStatus.FAILED
            assert target.policy_status is PolicyStatus.ALLOWED
            assert target.incremental_value > 0
            assert target.execution_status == "PLANNED"
            assert target.provider_action_id is None
            assert target.intervention_id is None
            assert plan.constraints_snapshot["enabled_actions"] == ["PAYMENT_LINK", "DO_NOTHING"]
            contacts = next(item for item in plan.resource_usage if item["key"] == "contacts")
            assert contacts == {"key": "contacts", "used": 1, "limit": 1}
    finally:
        cleanup()


def test_optimize_endpoint_queues_and_rejects_invalid_transition() -> None:
    cleanup()
    try:
        batch_id = client.post("/recovery-batches/demo", json={"payment_count": 2}).json()["id"]
        queued = Mock(id="task-27")
        with patch("app.api.recovery_batches.plan_recovery_batch_task.delay", return_value=queued): response = client.post(f"/recovery-batches/{batch_id}/optimize", json={})
        assert response.status_code == 202 and response.json()["status"] == "QUEUED"
        assert client.post(f"/recovery-batches/{batch_id}/optimize", json={}).status_code == 409
    finally: cleanup()


def test_execution_stopping_rules_do_not_fake_success() -> None:
    cleanup()
    try:
        _, plan_id = planned_batch(3)
        with SessionLocal() as db:
            assignments = db.scalars(select(OptimizationAssignment).where(OptimizationAssignment.plan_id == plan_id).order_by(OptimizationAssignment.id)).all()
            assignments[0].selected_action = RecoveryAction.DO_NOTHING
            assignments[1].selected_action = RecoveryAction.EMAIL
            assignments[2].policy_status = PolicyStatus.REQUIRES_APPROVAL
            db.commit(); ids = [item.id for item in assignments]
        assert execute_recovery_assignment_task.run(ids[0])["status"] == "NO_ACTION"
        assert execute_recovery_assignment_task.run(ids[1])["status"] == "MANUAL_REQUIRED"
        assert execute_recovery_assignment_task.run(ids[2])["status"] == "APPROVAL_REQUIRED"
        with SessionLocal() as db: assert db.query(Intervention).count() == 0
    finally: cleanup()


def test_payment_link_assignment_uses_planned_action_and_is_idempotent() -> None:
    cleanup()
    try:
        _, plan_id = planned_batch(1)
        with SessionLocal() as db:
            assignment = db.scalar(select(OptimizationAssignment).where(OptimizationAssignment.plan_id == plan_id)); assignment.selected_action = RecoveryAction.PAYMENT_LINK; db.commit(); assignment_id = assignment.id
        class FakeRecoveryService:
            calls = 0
            async def execute_payment_link(self, **kwargs):
                self.calls += 1
                return RecoveryExecutionResult("razorpay", "PAYMENT_LINK", True, "plink_phase27", "https://rzp.io/i/test", "created", "stable-test-reference")
        service = FakeRecoveryService()
        with patch("app.orchestration.nodes.get_recovery_service", return_value=service):
            first = execute_recovery_assignment_task.run(assignment_id); second = execute_recovery_assignment_task.run(assignment_id)
        assert first["status"] == "AWAITING_PAYMENT" and second["skipped"] is True
        assert service.calls == 1
        with SessionLocal() as db:
            assert db.query(Intervention).count() == 1
            persisted = db.get(OptimizationAssignment, assignment_id)
            assert persisted.provider_action_id == "plink_phase27"
            assert persisted.payment_url == "https://rzp.io/i/test"
    finally: cleanup()


def test_execute_before_ready_is_rejected() -> None:
    cleanup()
    try:
        batch_id = client.post("/recovery-batches/demo", json={"payment_count": 1}).json()["id"]
        assert client.post(f"/recovery-batches/{batch_id}/execute").status_code == 409
    finally: cleanup()


def test_get_batch_reconciles_terminal_async_assignments() -> None:
    cleanup()
    try:
        batch_id, plan_id = planned_batch(2)
        with SessionLocal() as db:
            batch = db.get(RecoveryBatch, batch_id)
            batch.status = "EXECUTING"
            batch.execution_started_at = batch.created_at
            assignments = db.scalars(
                select(OptimizationAssignment).where(
                    OptimizationAssignment.plan_id == plan_id
                )
            ).all()
            assignments[0].execution_status = "AWAITING_PAYMENT"
            assignments[1].execution_status = "FAILED"
            db.commit()
        response = client.get(f"/recovery-batches/{batch_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "COMPLETED"
        assert response.json()["execution_completed_at"] is not None
        assert client.post(f"/recovery-batches/{batch_id}/execute").status_code == 409
    finally:
        cleanup()
