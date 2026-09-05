import { apiClient } from "./client";
import type { InterventionLedgerPage } from "../types/intervention";

export async function getInterventions(params: {
  page: number;
  search?: string;
  status?: string;
  provider?: string;
}): Promise<InterventionLedgerPage> {
  const response = await apiClient.get<InterventionLedgerPage>("/interventions", {
    params: { ...params, page_size: 20 },
  });
  return response.data;
}
