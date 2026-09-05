export type PaymentStatus = "PENDING" | "FAILED" | "RECOVERED" | "SUCCEEDED" | "CANCELLED";
export type InterventionStatus = "PLANNED" | "EXECUTED" | "SUCCEEDED" | "FAILED" | "CANCELLED";
export type PolicyStatus = "ALLOWED" | "REJECTED" | "REQUIRES_APPROVAL";

export interface RankedAction {
  action: string;
  recovery_probability: number;
  intervention_cost: number;
  incentive_cost: number;
  expected_gross_value: number;
  expected_net_value: number;
  incremental_value: number;
}

export interface PolicyDecision {
  action: string;
  allowed: boolean;
  reason: string;
}

export interface RecoveryEvaluation {
  recommended_action: string;
  recovery_probability: number;
  expected_net_value: number;
  incremental_value: number;
  ranked_actions: RankedAction[];
  policy_decisions: PolicyDecision[];
}

export interface PaymentRow {
  id: number;
  amount: string;
  payment_method: string;
  failure_reason: string | null;
  status: PaymentStatus;
  recovery_action?: string;
  intervention_status?: InterventionStatus;
  recovery_probability?: number;
  incremental_value?: number;
}

export interface InterventionRow {
  id: number;
  payment_id: number;
  action: string;
  provider: string | null;
  provider_action_id: string | null;
  provider_status: string | null;
  status: InterventionStatus;
  executed_at: string | null;
}
