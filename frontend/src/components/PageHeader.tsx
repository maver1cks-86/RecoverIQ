interface PageHeaderProps { eyebrow?: string; title: string; description: string }

export function PageHeader({ eyebrow = "Operations", title, description }: PageHeaderProps) {
  return <header className="page-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-description">{description}</p></div></header>;
}
