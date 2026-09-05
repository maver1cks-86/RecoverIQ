export interface LivePortfolioSummary { failed_payments:number; recovered_payments:number; revenue_at_risk:string; recovered_revenue:string; recovery_rate:number; active_interventions:number; recorded_expected_value:string }
export interface InterventionMixItem { action:string; count:number }
export interface RecentIntervention { intervention_id:number; payment_id:number; action:string; status:string; provider:string|null; provider_status:string|null; expected_value:string; created_at:string }
export interface RecentRecovery { payment_id:number; recovered_amount:string; action:string; provider:string|null; completed_at:string|null }
export interface OfflineStrategy { strategy:"BASELINE"|"ML_DECISION"|"OPTIMIZED"; payments:number; net_value:string; recovery_rate:number; uplift_amount:string; uplift_percent:number }
export interface DashboardOverview { portfolio:LivePortfolioSummary; intervention_mix:InterventionMixItem[]; recent_interventions:RecentIntervention[]; recent_recoveries:RecentRecovery[]; offline_evaluation:{ label:string; solver_status:string; strategies:OfflineStrategy[] } }
