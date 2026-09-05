import { apiClient } from "./client"; import type { OptimizationConstraints,OptimizationResult,PortfolioMetadata,WhatIfProposal } from "../types/optimization";
export async function getOptimizationPortfolio(){const {data}=await apiClient.get<PortfolioMetadata>("/optimization/portfolio");return data}
export async function runOptimization(constraints:OptimizationConstraints){const {data}=await apiClient.post<OptimizationResult>("/optimization/run",constraints);return data}
export async function parseWhatIf(prompt:string,current_constraints:OptimizationConstraints){const {data}=await apiClient.post<WhatIfProposal>("/copilot/what-if/parse",{prompt,current_constraints});return data}
