from pydantic import BaseModel, Field


class EvaluationDataset(BaseModel):
    type: str
    role: str
    total_records: int
    train_records: int
    validation_records: int
    test_records: int


class BaselineEvaluation(BaseModel):
    net_recovery: float
    recovery_rate: float


class UnconstrainedEvaluation(BaseModel):
    net_recovery: float
    improvement: float
    relative_improvement_percent: float
    constraint_status: str


class RecoverIQEvaluation(BaseModel):
    net_recovery: float
    improvement: float
    relative_improvement_percent: float
    recovery_rate: float
    solver_status: str


class EvaluationConstraints(BaseModel):
    total_recovery_spend: float
    incentive_budget: float
    retry_capacity: int
    contact_capacity: int
    whatsapp_capacity: int
    max_incentive_actions: int
    max_human_escalations: int
    solver_timeout_ms: int


class ScaleBenchmark(BaseModel):
    payments: int
    feature_prep_seconds: float
    ml_scoring_seconds: float
    policy_economics_seconds: float
    solver_seconds: float
    total_seconds: float
    status: str


class EvaluationSummary(BaseModel):
    evaluation_name: str
    dataset: EvaluationDataset
    baseline: BaselineEvaluation
    unconstrained_ml: UnconstrainedEvaluation
    recoveriq: RecoverIQEvaluation
    constraints: EvaluationConstraints
    scale_benchmarks: list[ScaleBenchmark]


class EvaluationAssignment(BaseModel):
    payment_id: str
    strategy: str
    action: str
    amount: float
    true_recovery_probability: float
    expected_gross_revenue: float
    expected_net_revenue: float
    intervention_cost: float
    incentive_cost: float


class EvaluationAssignmentPage(BaseModel):
    artifact: str
    columns: list[str]
    items: list[EvaluationAssignment]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int

