import type { RunStatus } from "../types";

const labels: Record<RunStatus, string> = {
  pending: "待处理",
  queued: "排队中",
  running: "运行中",
  cancelling: "取消中",
  cancelled: "已取消",
  success: "完成",
  failed: "失败",
  unknown: "未知",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  return <span className={`status status-${status}`}>{labels[status]}</span>;
}
