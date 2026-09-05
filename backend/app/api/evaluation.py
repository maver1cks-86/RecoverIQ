from fastapi import APIRouter, Query

from app.schemas.evaluation import EvaluationAssignmentPage, EvaluationSummary
from app.services.evaluation_service import get_evaluation_assignments, get_evaluation_summary


router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/summary", response_model=EvaluationSummary)
def evaluation_summary() -> EvaluationSummary:
    return get_evaluation_summary()


@router.get("/assignments", response_model=EvaluationAssignmentPage)
def evaluation_assignments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    action: str | None = None,
    strategy: str | None = None,
) -> EvaluationAssignmentPage:
    return get_evaluation_assignments(page, page_size, search, action, strategy)

