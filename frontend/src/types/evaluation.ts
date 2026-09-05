export interface EvaluationSummary {
  evaluation_name: string;
  dataset: { type: string; role: string; total_records: number; train_records: number; validation_records: number; test_records: number };
  baseline: { net_recovery: number; recovery_rate: number };
  unconstrained_ml: { net_recovery: number; improvement: number; relative_improvement_percent: number; constraint_status: string };
  recoveriq: { net_recovery: number; improvement: number; relative_improvement_percent: number; recovery_rate: number; solver_status: string };
  constraints: { total_recovery_spend: number; incentive_budget: number; retry_capacity: number; contact_capacity: number; whatsapp_capacity: number; max_incentive_actions: number; max_human_escalations: number; solver_timeout_ms: number };
  scale_benchmarks: { payments: number; feature_prep_seconds: number; ml_scoring_seconds: number; policy_economics_seconds: number; solver_seconds: number; total_seconds: number; status: string }[];
}

export interface EvaluationAssignment {
  payment_id: string; strategy: string; action: string; amount: number;
  true_recovery_probability: number; expected_gross_revenue: number; expected_net_revenue: number;
  intervention_cost: number; incentive_cost: number;
}

export interface EvaluationAssignmentPage {
  artifact: string; columns: string[]; items: EvaluationAssignment[]; page: number; page_size: number; total: number;
}
