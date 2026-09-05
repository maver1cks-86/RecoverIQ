export interface CopilotContext { page?:string; payment_id?:number; optimization_payment_id?:string }
export interface CopilotResponse { answer:string; facts:{label:string;value:string}[]; tools_used:string[]; suggested_questions:string[]; ai_available:boolean; data_scope:string }
