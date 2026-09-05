import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getPaymentAudit } from "../api/audit";
import { PageHeader } from "../components/PageHeader";
import { RecoveryTimeline } from "../components/RecoveryTimeline";
import { SectionCard } from "../components/SectionCard";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import type { PaymentAudit } from "../types/audit";
import { formatINR } from "../utils/format";

export function AuditTrailPage() {
  const [searchParams] = useSearchParams();
  const linkedPaymentId = searchParams.get("payment_id") ?? "";
  const [query, setQuery] = useState(linkedPaymentId);
  const [audit, setAudit] = useState<PaymentAudit | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadAudit = async (value: string) => {
    const id = Number(value);
    if (!Number.isInteger(id) || id < 1) {
      setError("Enter a valid numeric payment ID.");
      return;
    }
    setLoading(true);
    setError("");
    setAudit(null);
    try {
      setAudit(await getPaymentAudit(id));
    } catch (requestError) {
      const status = (requestError as { response?: { status?: number } }).response?.status;
      setError(status === 404 ? `Payment #${id} was not found in the live database.` : "The audit service is unavailable.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (linkedPaymentId) {
      setQuery(linkedPaymentId);
      void loadAudit(linkedPaymentId);
    }
  }, [linkedPaymentId]);

  const search = (event: FormEvent) => {
    event.preventDefault();
    void loadAudit(query);
  };
  const ask = () => audit && window.dispatchEvent(new CustomEvent("recoveriq:copilot", { detail: { page: "audit", payment_id: audit.payment_id, prompt: `What happened to payment ${audit.payment_id}?` } }));

  return <><PageHeader eyebrow="Decision explainability" title="Audit trail" description="Inspect the persisted chain behind a recovery decision. Missing events remain missing; this view never synthesizes history."/><SectionCard title="Payment recovery memory" description="Live system / database data"><form className="audit-search" onSubmit={search}><label htmlFor="audit-payment">Payment ID</label><input id="audit-payment" inputMode="numeric" value={query} onChange={event=>setQuery(event.target.value)} placeholder="e.g. 985"/><button disabled={loading}>Load audit trace</button></form>{loading&&<LoadingState label="Loading persisted recovery events"/>}{!loading&&error&&<ErrorState title="Audit trace unavailable" description={error}/>} {!loading&&!error&&!audit&&<EmptyState title="No audit record selected" description="Enter a live database payment ID to inspect its recorded decision, policy, intervention, provider, webhook, and outcome events."/>}{audit&&<div className="audit-result"><div className="audit-summary"><div><span>Payment</span><strong>#{audit.payment_id}</strong></div><div><span>Amount</span><strong>{formatINR(audit.amount)} {audit.currency}</strong></div><div><span>Method</span><strong>{audit.payment_method}</strong></div><div><span>Current state</span><StatusBadge status={audit.current_status}/></div><button onClick={ask}><span>✦</span> Ask Copilot</button></div><div className="audit-provenance"><i/> LIVE SYSTEM / DATABASE DATA · {audit.events.length} persisted events</div><RecoveryTimeline events={audit.events}/></div>}</SectionCard></>;
}
