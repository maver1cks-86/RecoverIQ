import { apiClient } from "./client";
import type { DashboardOverview } from "../types/dashboard";
export async function getDashboardOverview(): Promise<DashboardOverview> { const { data } = await apiClient.get<DashboardOverview>("/dashboard/overview"); return data; }
