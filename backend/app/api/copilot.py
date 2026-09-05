from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.copilot import CopilotChatRequest, CopilotChatResponse, WhatIfConstraintChanges, WhatIfParseRequest, WhatIfParseResponse
from app.services.copilot_service import answer_copilot
from app.services.llm_provider import GroundedLLMProvider


router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.get("/status")
def copilot_status() -> dict[str, str | bool]:
    provider = GroundedLLMProvider()
    return {
        "ai_available": provider.configured,
        "provider": "configured" if provider.configured else "not_configured",
        "deterministic_explanations": True,
    }


@router.post("/chat", response_model=CopilotChatResponse)
def copilot_chat(request: CopilotChatRequest, db: Session = Depends(get_db)) -> CopilotChatResponse:
    return answer_copilot(db, request)


@router.post(
    "/what-if/parse",
    response_model=WhatIfParseResponse,
    response_model_exclude_none=True,
)
def parse_what_if(request: WhatIfParseRequest) -> WhatIfParseResponse:
    raw = GroundedLLMProvider().parse_what_if_constraints(request.prompt)
    if raw is None:
        raise HTTPException(503, "What-if interpretation is unavailable; no constraints were applied.")
    try:
        proposed = WhatIfConstraintChanges.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors(include_url=False)) from exc
    return WhatIfParseResponse(
        proposed_changes=proposed,
        current_constraints=request.current_constraints,
    )
