import { apiClient } from "./client"; import type { PaymentAudit } from "../types/audit";
export async function getPaymentAudit(paymentId:number){const {data}=await apiClient.get<PaymentAudit>(`/audit/payments/${paymentId}`);return data}
