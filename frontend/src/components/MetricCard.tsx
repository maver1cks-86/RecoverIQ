interface MetricCardProps { label: string; value?: string; note: string; accent?: boolean }

export function MetricCard({ label, value, note, accent }: MetricCardProps) {
  return <article className={`metric-card ${accent ? "metric-accent" : ""}`}><div className="metric-top"><span>{label}</span><span className="metric-dot" /></div><strong>{value ?? "—"}</strong><p>{note}</p></article>;
}
