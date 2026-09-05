import { apiClient } from "./client"; import type { CopilotContext,CopilotResponse } from "../types/copilot";
export async function getCopilotStatus(){const {data}=await apiClient.get<{ai_available:boolean;provider:string;deterministic_explanations:boolean}>("/copilot/status");return data}
export async function askCopilot(message:string,context:CopilotContext){const {data}=await apiClient.post<CopilotResponse>("/copilot/chat",{message,context});return data}
