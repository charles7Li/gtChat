import { FormEvent, useState } from "react";
import { api } from "../api";
import { ErrorNotice } from "../components/ErrorNotice";
import { RunTimeline } from "../components/RunTimeline";
import { StatusBadge } from "../components/StatusBadge";
import type { ChatRun, RunStatus } from "../types";

export function ChatPage({ onOpenReports }: { onOpenReports: () => void }) {
  const [query, setQuery] = useState("宠物用品趋势分析");
  const [taskType, setTaskType] = useState("趋势分析");
  const [allowLive, setAllowLive] = useState(false);
  const [status, setStatus] = useState<RunStatus>("pending");
  const [run, setRun] = useState<ChatRun | null>(null);
  const [error, setError] = useState("");

  async function runWorkflow() {
    setStatus("running");
    setError("");
    try {
      const result = await api.runChat(`${taskType}: ${query}`, allowLive);
      setRun(result);
      setStatus("success");
    } catch (exc) {
      setStatus("failed");
      setError(exc instanceof Error ? exc.message : "Run failed");
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await runWorkflow();
  }

  function startNew() {
    setQuery("");
    setRun(null);
    setError("");
    setStatus("pending");
  }

  return (
    <section className="content-grid two-col">
      <form className="panel" onSubmit={submit}>
        <label>
          任务类型
          <select value={taskType} onChange={(event) => setTaskType(event.target.value)}>
            <option>趋势分析</option>
            <option>仿拍方案</option>
            <option>参考视频拆解</option>
            <option>热点分析</option>
          </select>
        </label>
        <label>
          需求
          <textarea value={query} onChange={(event) => setQuery(event.target.value)} rows={8} />
        </label>
        <label className="switch">
          <input type="checkbox" checked={allowLive} onChange={(event) => setAllowLive(event.target.checked)} />
          允许 live 外部调用
        </label>
        <p className="hint">默认走本地/offline 能力。完整采集流程需要显式打开 live。</p>
        <div className="actions">
          <button className="primary" disabled={status === "running" || !query.trim()}>
            {status === "running" ? "Running..." : "Run workflow"}
          </button>
          <button type="button" onClick={startNew}>New</button>
        </div>
      </form>

      <section className="panel">
        <div className="panel-head">
          <h2>Run status</h2>
          <StatusBadge status={status} />
        </div>
        <RunTimeline status={status} />
        {error && <ErrorNotice message={error} onRetry={() => void runWorkflow()} />}
        {run && (
          <div className="result-list">
            <div><span>Route</span><strong>{run.route}</strong></div>
            <div><span>Report</span><strong>{run.report_path || "pending"}</strong></div>
            <div><span>Trace</span><strong>{run.trace_path || "pending"}</strong></div>
            <button onClick={onOpenReports}>Open reports</button>
          </div>
        )}
      </section>
    </section>
  );
}
