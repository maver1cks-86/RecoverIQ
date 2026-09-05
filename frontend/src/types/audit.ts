export type AuditDetailValue = string | number | boolean | null | AuditDetailValue[] | { [key:string]: AuditDetailValue };
export interface AuditEvent { event_type:string; title:string; status:string|null; timestamp:string|null; details:Record<string,AuditDetailValue> }
export interface PaymentAudit { payment_id:number; amount:string; currency:string; payment_method:string; current_status:string; source:string; events:AuditEvent[] }
