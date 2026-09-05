const inr=new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR",minimumFractionDigits:2,maximumFractionDigits:2});
export const formatINR=(value:string|number)=>inr.format(Number(value));
export const formatPercent=(value:number)=>`${value.toFixed(2)}%`;
export function formatDateTime(value:string|null){if(!value)return "—";return new Intl.DateTimeFormat("en-IN",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}).format(new Date(value))}
