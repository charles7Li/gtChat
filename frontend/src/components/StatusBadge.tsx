import type { RunStatus } from "../types";

export function StatusBadge({ status }: { status: RunStatus | string }) {
  return <span className={`status status-${status}`}>{status}</span>;
}
