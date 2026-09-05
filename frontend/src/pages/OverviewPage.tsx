import { Link } from "react-router-dom";
import { EmptyState,ErrorStateWithRetry } from "../components/States";
import { InterventionActionBadge } from "../components/InterventionActionBadge";
import { InterventionMix } from "../components/InterventionMix";
import { LoadingSkeleton } from "../components/LoadingSkeleton";
import { MetricCard } from "../components/MetricCard";
import { PageHeader } from "../components/PageHeader";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { StrategyComparison } from "../components/StrategyComparison";
import { useDashboard } from "../hooks/useDashboard";
import { formatDateTime,formatINR,formatPercent } from "../utils/format";

export function OverviewPage(){
 const {data,loading,error,retry}=useDashboard();
 if(loading)return <><PageHeader eyebrow="Revenue command center" title="Recovery overview" description="Loading live portfolio intelligence and recovery performance."/><LoadingSkeleton/></>;
 if(error||!data)return <><PageHeader eyebrow="Revenue command center" title="Recovery overview" description="Monitor recovery health and portfolio value."/><SectionCard title="Live system data"><ErrorStateWithRetry description={error??"No dashboard response was returned."} onRetry={()=>void retry()}/></SectionCard></>;
 const {portfolio}=data; const hasInterventions=data.intervention_mix.some(item=>item.count>0);
 return <>
  <PageHeader eyebrow="Revenue command center" title="Recovery overview" description="From failed payment to economically optimal intervention—tracked across the live recovery portfolio."/>
  <div className="data-label"><span className="live-pulse"/>LIVE SYSTEM DATA <small>Current local database</small></div>
  <div className="metric-grid">
   <MetricCard label="Revenue at risk" value={formatINR(portfolio.revenue_at_risk)} note={`${portfolio.failed_payments} unresolved failed payments`} accent/>
   <MetricCard label="Failed payments" value={portfolio.failed_payments.toLocaleString("en-IN")} note="Current recovery candidates"/>
   <MetricCard label="Recovered payments" value={portfolio.recovered_payments.toLocaleString("en-IN")} note={`${formatPercent(portfolio.recovery_rate)} live recovery rate`}/>
   <MetricCard label="Recovered revenue" value={formatINR(portfolio.recovered_revenue)} note="Confirmed successful outcomes"/>
   <MetricCard label="Active interventions" value={portfolio.active_interventions.toLocaleString("en-IN")} note={`${formatINR(portfolio.recorded_expected_value)} recorded expected value`}/>
  </div>
  <section className="decision-story" aria-label="RecoverIQ decision pipeline"><div><span>01</span><strong>Predict</strong><small>Recovery probability by action</small></div><i>→</i><div><span>02</span><strong>Value</strong><small>Incremental economic impact</small></div><i>→</i><div><span>03</span><strong>Constrain</strong><small>Policy and scarce resources</small></div><i>→</i><div><span>04</span><strong>Orchestrate</strong><small>LangGraph to Razorpay</small></div></section>
  <div className="data-label offline-label">OFFLINE / FROZEN TEST SET EVALUATION <small>Never combined with live portfolio metrics</small></div>
  <SectionCard title="Recovery performance" description="Baseline → predictive intelligence → constrained portfolio optimization"><StrategyComparison strategies={data.offline_evaluation.strategies} solverStatus={data.offline_evaluation.solver_status}/></SectionCard>
  <div className="overview-grid dashboard-grid">
   <SectionCard title="Intervention mix" description="Real actions recorded in the live database">{hasInterventions?<InterventionMix items={data.intervention_mix}/>:<EmptyState title="No interventions recorded" description="Run a recovery workflow to see its model-selected action mix."/>}</SectionCard>
   <section className="next-step-card"><span className="eyebrow">Next best step</span><h2>Allocate recovery resources across the portfolio.</h2><p>Move from payment-level predictions to policy-aware, constrained allocation that maximizes expected net revenue.</p><Link className="primary-cta" to="/optimization">Optimize recovery <span>→</span></Link><div className="secondary-links"><Link to="/recovery-queue">Open Recovery Queue</Link><Link to="/audit-trail">View Audit Trail</Link></div></section>
  </div>
  <div className="overview-grid dashboard-grid">
   <SectionCard title="Recent interventions" description="Latest recommendations and provider executions">{data.recent_interventions.length?<div className="compact-table"><table><thead><tr><th>Payment</th><th>Action</th><th>Status</th><th>Provider</th><th>Expected value</th><th>Created</th></tr></thead><tbody>{data.recent_interventions.map(item=><tr key={item.intervention_id}><td>#{item.payment_id}</td><td><InterventionActionBadge action={item.action}/></td><td><StatusBadge status={item.status}/></td><td><span className="provider-cell">{item.provider??"Internal"}<small>{item.provider_status??"—"}</small></span></td><td>{formatINR(item.expected_value)}</td><td>{formatDateTime(item.created_at)}</td></tr>)}</tbody></table></div>:<EmptyState title="No recent interventions" description="Workflow executions will appear here as soon as they are persisted."/>}</SectionCard>
   <SectionCard title="Recent recoveries" description="Confirmed outcomes closed by provider events">{data.recent_recoveries.length?<div className="recovery-list">{data.recent_recoveries.map(item=><article key={`${item.payment_id}-${item.completed_at}`}><div className="recovery-check">✓</div><div><strong>Payment #{item.payment_id}</strong><span><InterventionActionBadge action={item.action}/>{item.provider??"Internal"}</span></div><div><strong>{formatINR(item.recovered_amount)}</strong><time>{formatDateTime(item.completed_at)}</time></div></article>)}</div>:<EmptyState title="No completed recoveries yet" description="Successful outcomes will appear after the webhook and Celery processing loop completes."/>}</SectionCard>
  </div>
 </>;
}
