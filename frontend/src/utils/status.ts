export type StatusTone = "positive" | "negative" | "warning" | "neutral" | "info";

const tones: Record<string, StatusTone> = {
  RECOVERED: "positive", SUCCEEDED: "positive", ALLOWED: "positive", processed: "positive", paid: "positive",
  FAILED: "negative", REJECTED: "negative", failed: "negative",
  REQUIRES_APPROVAL: "warning", PENDING: "warning", PLANNED: "warning",
  EXECUTED: "info", processing: "info", created: "info",
  CANCELLED: "neutral",
};

export function statusTone(status: string): StatusTone {
  return tones[status] ?? "neutral";
}

export function statusLabel(status: string): string {
  return status.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}
