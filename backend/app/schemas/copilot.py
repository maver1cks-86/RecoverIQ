from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.optimization import OptimizationConstraintsRequest


class CopilotContext(BaseModel):
    page: str | None = Field(default=None, max_length=50)
    payment_id: int | None = Field(default=None, ge=1)
    optimization_payment_id: str | None = Field(default=None, min_length=1, max_length=80)


class CopilotChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    context: CopilotContext | None = None


class SupportingFact(BaseModel):
    label: str
    value: str


class CopilotChatResponse(BaseModel):
    answer: str
    facts: list[SupportingFact]
    tools_used: list[str]
    suggested_questions: list[str]
    ai_available: bool
    data_scope: str


class WhatIfConstraintChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_budget: float | None = Field(default=None, ge=0)
    incentive_budget: float | None = Field(default=None, ge=0)
    max_retries: int | None = Field(default=None, ge=0)
    max_contacts: int | None = Field(default=None, ge=0)
    max_whatsapp: int | None = Field(default=None, ge=0)
    max_incentive_actions: int | None = Field(default=None, ge=0)
    max_human_escalations: int | None = Field(default=None, ge=0)
    solver_timeout_ms: int | None = Field(default=None, ge=1000, le=120000)

    @model_validator(mode="after")
    def require_at_least_one_change(self):
        if not self.model_dump(exclude_none=True):
            raise ValueError("No supported constraint changes were found.")
        return self


class WhatIfParseRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    current_constraints: OptimizationConstraintsRequest


class WhatIfParseResponse(BaseModel):
    proposed_changes: WhatIfConstraintChanges
    current_constraints: OptimizationConstraintsRequest
    requires_confirmation: bool = True
    applied: bool = False
