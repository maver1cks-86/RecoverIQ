interface SectionCardProps { title: string; description?: string; children: React.ReactNode; className?: string }

export function SectionCard({ title, description, children, className = "" }: SectionCardProps) {
  return <section className={`section-card ${className}`}><div className="section-heading"><div><h2>{title}</h2>{description && <p>{description}</p>}</div></div>{children}</section>;
}
