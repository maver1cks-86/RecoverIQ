import { apiClient } from "./client"; import type { AssignmentPage,BatchConstraints,BatchSummary,RecoveryBatch } from "../types/recoveryBatch";
export async function createDemoBatch(payment_count=20){const {data}=await apiClient.post<RecoveryBatch>("/recovery-batches/demo",{payment_count});return data}
export async function getRecoveryBatch(id:number){const {data}=await apiClient.get<RecoveryBatch>(`/recovery-batches/${id}`);return data}
export async function optimizeRecoveryBatch(id:number,constraints:BatchConstraints){const {data}=await apiClient.post(`/recovery-batches/${id}/optimize`,{constraints});return data}
export async function executeRecoveryBatch(id:number){const {data}=await apiClient.post(`/recovery-batches/${id}/execute`);return data}
export async function getBatchSummary(id:number){const {data}=await apiClient.get<BatchSummary>(`/recovery-batches/${id}/summary`);return data}
export async function getBatchAssignments(id:number,page=1,action="",execution=""){const {data}=await apiClient.get<AssignmentPage>(`/recovery-batches/${id}/assignments`,{params:{page,page_size:20,action:action||undefined,execution_status:execution||undefined}});return data}
