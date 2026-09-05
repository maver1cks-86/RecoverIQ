export interface InterventionLedgerItem {
  intervention_id: number;
  payment_id: number;
  action: string;
  provider: string | null;
  provider_action_id: string | null;
  provider_status: string | null;
  status: string;
  executed_at: string | null;
  created_at: string;
}

export interface InterventionLedgerPage {
  items: InterventionLedgerItem[];
  page: number;
  page_size: number;
  total: number;
}
