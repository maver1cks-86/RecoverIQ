export function LoadingState({ label = "Loading data" }: { label?: string }) {
  return <div className="state-box" role="status"><span className="spinner"/><strong>{label}</strong><p>Contacting the RecoverIQ API.</p></div>;
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="state-box"><div className="empty-mark">RI</div><strong>{title}</strong><p>{description}</p></div>;
}

export function ErrorState({ title = "Data unavailable", description }: { title?: string; description: string }) {
  return <div className="state-box state-error"><div className="error-mark">!</div><strong>{title}</strong><p>{description}</p></div>;
}

export function ErrorStateWithRetry({ description, onRetry }: { description: string; onRetry: () => void }) {
  return <div className="state-box state-error"><div className="error-mark">!</div><strong>Dashboard unavailable</strong><p>{description}</p><button className="retry-button" onClick={onRetry}>Try again</button></div>;
}
