import { apiClient } from "./client";
import type { EvaluationAssignmentPage, EvaluationSummary } from "../types/evaluation";

export async function getEvaluationSummary() {
  const { data } = await apiClient.get<EvaluationSummary>("/evaluation/summary");
  return data;
}

export async function getEvaluationAssignments(page = 1, search = "", action = "", strategy = "") {
  const { data } = await apiClient.get<EvaluationAssignmentPage>("/evaluation/assignments", { params: { page, page_size: 15, search: search || undefined, action: action || undefined, strategy: strategy || undefined } });
  return data;
}
