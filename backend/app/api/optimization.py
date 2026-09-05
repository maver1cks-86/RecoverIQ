from fastapi import APIRouter

from app.schemas.optimization import (
    OptimizationConstraintsRequest,
    OptimizationRunResponse,
    PortfolioMetadataResponse,
)
from app.services.optimization_service import portfolio_metadata, run_optimization


router = APIRouter(prefix="/optimization", tags=["optimization"])


@router.get("/portfolio", response_model=PortfolioMetadataResponse)
def get_portfolio() -> PortfolioMetadataResponse:
    return portfolio_metadata()


@router.post("/run", response_model=OptimizationRunResponse)
def optimize_portfolio(
    request: OptimizationConstraintsRequest,
) -> OptimizationRunResponse:
    return run_optimization(request)
