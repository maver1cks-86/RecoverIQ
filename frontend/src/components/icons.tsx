interface IconProps { className?: string }

function Icon({ children, className = "" }: React.PropsWithChildren<IconProps>) {
  return <svg className={className} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>;
}

export const GridIcon = (p: IconProps) => <Icon {...p}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></Icon>;
export const QueueIcon = (p: IconProps) => <Icon {...p}><path d="M4 6h16M4 12h16M4 18h10"/><circle cx="18" cy="18" r="2"/></Icon>;
export const OptimizeIcon = (p: IconProps) => <Icon {...p}><path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/><path d="m3 8 6-4 6 7 6-5"/></Icon>;
export const LinkIcon = (p: IconProps) => <Icon {...p}><path d="M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1.1-1.1"/></Icon>;
export const AuditIcon = (p: IconProps) => <Icon {...p}><path d="M9 5H5v16h14V5h-4"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="m8 13 2 2 5-5M8 19h8"/></Icon>;
export const SearchIcon = (p: IconProps) => <Icon {...p}><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></Icon>;
