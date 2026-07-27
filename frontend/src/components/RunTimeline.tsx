import type { RunStatus } from "../types";

const steps: Step[] = ["plan", "route", "collect", "analyze", "report"];
const labels: Record<string, string> = { plan: "规划", route: "路由", collect: "数据准备", analyze: "分析/方案", report: "报告" };
type Step = "plan" | "route" | "collect" | "analyze" | "report";
function category(name: string): Step {
  if (name === "plan") return "plan";
  if (name === "route") return "route";
  if (["collect", "memory_load", "clean", "load_latest_search_results", "commercial_data_import", "local_video_analyze"].includes(name)) return "collect";
  if (["trend_analyze", "pattern_extract", "video_pattern_extract", "evidence_pack", "imitation_plan", "review"].includes(name)) return "analyze";
  if (["report", "commercial_report", "memory_write", "store"].includes(name)) return "report";
  return "analyze";
}

export function RunTimeline({ status, stages = [] }: { status: RunStatus; stages?: Array<{ name: string; status: string }> }) {
  const active = new Set(stages.filter((stage) => stage.status === "running" || stage.status === "success" || stage.status === "warning").map((stage) => category(stage.name)));
  const activeIndex = steps.findIndex((step) => active.has(step));
  const current = status === "pending" || status === "queued" ? 0 : status === "running" ? Math.max(1, activeIndex) : steps.length - 1;
  return (
    <ol className="timeline" aria-label="任务进度">
      {steps.map((step, index) => {
        const className = status === "failed" && index === current ? "failed" : index <= current ? "current" : "";
        return (
          <li key={step} className={className}>
            <span aria-hidden="true" />
            {labels[step]}
          </li>
        );
      })}
    </ol>
  );
}
