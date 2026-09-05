interface Column { key: string; label: string; align?: "left" | "right" }
interface DataTableProps { columns: Column[]; children?: React.ReactNode; emptyTitle: string; emptyDescription: string }

export function DataTable({ columns, children, emptyTitle, emptyDescription }: DataTableProps) {
  return <div className="table-wrap"><table><thead><tr>{columns.map((column) => <th key={column.key} className={column.align === "right" ? "align-right" : ""}>{column.label}</th>)}</tr></thead>{children && <tbody>{children}</tbody>}</table>{!children && <EmptyTable title={emptyTitle} description={emptyDescription}/>}<div className="table-footer"><span>0 results</span><div><button disabled>Previous</button><span>Page 1</span><button disabled>Next</button></div></div></div>;
}

function EmptyTable({ title, description }: { title: string; description: string }) {
  return <div className="table-empty"><div className="empty-lines"><i/><i/><i/></div><strong>{title}</strong><p>{description}</p></div>;
}
