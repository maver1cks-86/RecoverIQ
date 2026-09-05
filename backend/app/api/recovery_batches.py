from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.decision.actions import RecoveryAction
from app.models.enums import PolicyStatus
from app.models.recovery_batch import OptimizationAssignment, RecoveryBatch
from app.schemas.recovery_batch import AssignmentPage, AssignmentResponse, BatchOptimizeRequest, BatchResponse, BatchSummary, DemoBatchRequest, JobAccepted
from app.services.recovery_batch_service import batch_summary, create_demo_batch, latest_plan, reconcile_batch_execution
from app.tasks.batch_tasks import execute_recovery_assignment_task, plan_recovery_batch_task
from app.services.batch_event_service import publish_assignment_state

router = APIRouter(prefix="/recovery-batches", tags=["recovery-batches"])


def _batch_response(batch: RecoveryBatch) -> BatchResponse:
    return BatchResponse(id=batch.id, merchant_id=batch.merchant_id, reference_id=batch.reference_id, source=batch.source, status=batch.status, payment_count=batch.payment_count, revenue_at_risk=batch.revenue_at_risk, error_message=batch.error_message, created_at=batch.created_at, planning_started_at=batch.planning_started_at, planning_completed_at=batch.planning_completed_at, execution_started_at=batch.execution_started_at, execution_completed_at=batch.execution_completed_at)


@router.post("/demo", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
def create_demo(request: DemoBatchRequest, db: Session = Depends(get_db)) -> BatchResponse:
    return _batch_response(create_demo_batch(db, request.payment_count, request.reference_id))


@router.get("/{batch_id}", response_model=BatchResponse)
def get_batch(batch_id: int, db: Session = Depends(get_db)) -> BatchResponse:
    batch = db.get(RecoveryBatch, batch_id)
    if batch is None: raise HTTPException(404, "Recovery batch not found")
    reconcile_batch_execution(db, batch)
    return _batch_response(batch)


@router.post("/{batch_id}/optimize", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
def optimize_batch(batch_id: int, request: BatchOptimizeRequest, db: Session = Depends(get_db)) -> JobAccepted:
    batch = db.get(RecoveryBatch, batch_id, with_for_update=True)
    if batch is None: raise HTTPException(404, "Recovery batch not found")
    if batch.status not in {"CREATED", "FAILED", "READY"}: raise HTTPException(409, f"Batch cannot be queued from status {batch.status}")
    if batch.execution_started_at is not None: raise HTTPException(409, "An execution-started batch cannot be replanned")
    batch.status = "QUEUED"; batch.error_message = None; db.commit()
    try:
        task = plan_recovery_batch_task.delay(batch_id, request.constraints.model_dump())
    except Exception as exc:
        batch = db.get(RecoveryBatch, batch_id); batch.status = "FAILED"; batch.error_message = "Planning queue unavailable"; db.commit()
        raise HTTPException(503, "Planning queue unavailable") from exc
    return JobAccepted(batch_id=batch_id, status="QUEUED", task_id=task.id)


@router.get("/{batch_id}/assignments", response_model=AssignmentPage)
def get_assignments(batch_id: int, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), action: RecoveryAction | None = None, execution_status: str | None = None, recovered: bool | None = None, db: Session = Depends(get_db)) -> AssignmentPage:
    if db.get(RecoveryBatch, batch_id) is None: raise HTTPException(404, "Recovery batch not found")
    plan = latest_plan(db, batch_id)
    if plan is None: return AssignmentPage(items=[], page=page, page_size=page_size, total=0)
    query = select(OptimizationAssignment).options(joinedload(OptimizationAssignment.payment)).where(OptimizationAssignment.plan_id == plan.id)
    if action is not None: query = query.where(OptimizationAssignment.selected_action == action)
    if execution_status: query = query.where(OptimizationAssignment.execution_status == execution_status)
    if recovered is True: query = query.where(OptimizationAssignment.execution_status == "RECOVERED")
    elif recovered is False: query = query.where(OptimizationAssignment.execution_status != "RECOVERED")
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = db.scalar(count_query) or 0
    rows = db.scalars(query.order_by(OptimizationAssignment.id).offset((page-1)*page_size).limit(page_size)).all()
    items = [AssignmentResponse(id=item.id, payment_id=item.payment_id, amount=item.payment.amount, failure_reason=item.payment.failure_reason, selected_action=item.selected_action.value, policy_status=item.policy_status.value, recovery_probability=item.recovery_probability, expected_value=item.expected_value, incremental_value=item.incremental_value, intervention_cost=item.intervention_cost, incentive_cost=item.incentive_cost, execution_status=item.execution_status, provider=item.provider, provider_action_id=item.provider_action_id, provider_status=item.provider_status, payment_url=item.payment_url, standalone_best_action=item.standalone_best_action, selected_rank=item.selected_rank, portfolio_agreement=item.portfolio_agreement, alternatives=item.alternatives, policy_evidence=item.policy_evidence) for item in rows]
    return AssignmentPage(items=items, page=page, page_size=page_size, total=total)


@router.post("/{batch_id}/execute", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
def execute_batch(batch_id: int, db: Session = Depends(get_db)) -> JobAccepted:
    batch = db.get(RecoveryBatch, batch_id, with_for_update=True)
    if batch is None: raise HTTPException(404, "Recovery batch not found")
    if batch.status != "READY": raise HTTPException(409, f"Batch execution requires READY status, found {batch.status}")
    plan = latest_plan(db, batch_id)
    if plan is None: raise HTTPException(409, "Batch has no persisted plan")
    assignments = db.scalars(select(OptimizationAssignment).where(OptimizationAssignment.plan_id == plan.id).with_for_update()).all()
    executable_ids = []
    for item in assignments:
        if item.policy_status is PolicyStatus.REJECTED: item.execution_status = "POLICY_REJECTED"
        elif item.policy_status is PolicyStatus.REQUIRES_APPROVAL: item.execution_status = "APPROVAL_REQUIRED"
        elif item.selected_action is RecoveryAction.DO_NOTHING: item.execution_status = "NO_ACTION"
        elif item.selected_action is RecoveryAction.PAYMENT_LINK: item.execution_status = "QUEUED"; executable_ids.append(item.id)
        else: item.execution_status = "MANUAL_REQUIRED"
    now = datetime.now(timezone.utc)
    batch.execution_started_at = now
    if executable_ids:
        batch.status = "EXECUTING"
    else:
        batch.status = "COMPLETED"
        batch.execution_completed_at = now
    db.commit()
    for item in assignments:
        publish_assignment_state(db, item)
    for assignment_id in executable_ids:
        execute_recovery_assignment_task.delay(assignment_id)
    return JobAccepted(batch_id=batch_id, status=batch.status, task_id=None)


@router.get("/{batch_id}/summary", response_model=BatchSummary)
def get_summary(batch_id: int, db: Session = Depends(get_db)) -> BatchSummary:
    try: data = batch_summary(db, batch_id)
    except LookupError as exc: raise HTTPException(404, "Recovery batch not found") from exc
    plan = data["plan"]
    return BatchSummary(batch=_batch_response(data["batch"]), plan_id=plan.id if plan else None, plan_version=plan.version if plan else None, solver_status=plan.solver_status if plan else None, observed_recovered_amount=data["observed_recovered_amount"], estimated_incremental_value=data["estimated_incremental_value"], action_allocation=data["action_allocation"], execution_counts=data["execution_counts"], constraint_utilization=data["constraint_utilization"], constraints_snapshot=data["constraints_snapshot"])
