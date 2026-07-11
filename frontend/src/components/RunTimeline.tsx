import type { RunStatus } from "../types";

const steps = ["简报", "路由", "分析", "报告"];

export function RunTimeline({ status }: { status: RunStatus }) {
  const current = status === "pending" ? 0 : status === "running" ? 2 : steps.length - 1;
  return (
    <ol className="timeline" aria-label="任务进度">
      {steps.map((step, index) => {
        const className = status === "failed" && index === current ? "failed" : index <= current ? "current" : "";
        return (
          <li key={step} className={className}>
            <span aria-hidden="true" />
            {step}
          </li>
        );
      })}
    </ol>
  );
}
