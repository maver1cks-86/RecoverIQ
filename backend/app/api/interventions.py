from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.intervention import InterventionListResponse
from app.services.intervention_service import list_interventions


router = APIRouter(prefix="/interventions", tags=["interventions"])


@router.get("", response_model=InterventionListResponse)
def interventions_list(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=40),
    provider: str | None = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
) -> InterventionListResponse:
    return list_interventions(
        db,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        provider=provider,
    )
