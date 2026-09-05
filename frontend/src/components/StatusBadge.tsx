import { statusLabel, statusTone } from "../utils/status";

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge status-${statusTone(status)}`}><span />{statusLabel(status)}</span>;
}
