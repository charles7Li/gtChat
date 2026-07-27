import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { BriefBuilder } from "../components/BriefBuilder";
import { ErrorNotice } from "../components/ErrorNotice";
import { RunTimeline } from "../components/RunTimeline";
import { StatusBadge } from "../components/StatusBadge";
import type { ChatRun, RunStatus } from "../types";

export function ChatPage({ onOpenReports }: { onOpenReports: () => void }) {
  const [query, setQuery] = useState("帮我找出宠物内容里最值得跟进的角度，并整理成可执行的拍摄方案。");
  const [taskType, setTaskType] = useState("趋势分析");
  const [outputTarget, setOutputTarget] = useState("策略报告");
  const [sourceContext, setSourceContext] = useState("本地结果");
  const [allowLive, setAllowLive] = useState(false);
  const [status, setStatus] = useState<RunStatus>("pending");
  const [run, setRun] = useState<ChatRun | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!run?.run_id || !["queued", "running"].includes(run.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.getChatRun(run.run_id);
        setRun(next);
        if (next.status === "success" || next.status === "failed") {
          setStatus(next.status === "success" ? "success" : "failed");
          if (next.error) setError(next.error);
          window.clearInterval(timer);
        }
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "无法读取任务状态");
      }
    }, 800);
    return () => window.clearInterval(timer);
  }, [run?.run_id, run?.status]);

  const composedBrief = `任务：${taskType}。输出：${outputTarget}。来源：${sourceContext}。简报：${query}`;

  async function runWorkflow() {
    setStatus("running");
    setError("");
    try {
      const result = await api.runChat(composedBrief, allowLive);
      setRun(result);
      setStatus(result.status === "success" ? "success" : "running");
    } catch (exc) {
      setStatus("failed");
      setError(exc instanceof Error ? exc.message : "运行失败");
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
    <section className="chat-layout">
      <form className="brief-panel" onSubmit={submit}>
        <div className="panel-intro">
          <p className="section-kicker">简报</p>
          <h2>把想法整理成一次任务</h2>
        </div>
        <BriefBuilder
          taskType={taskType}
          outputTarget={outputTarget}
          sourceContext={sourceContext}
          allowLive={allowLive}
          onTaskTypeChange={setTaskType}
          onOutputTargetChange={setOutputTarget}
          onSourceContextChange={setSourceContext}
          onAllowLiveChange={setAllowLive}
        />
        <label className="brief-input">
          需求
          <textarea value={query} onChange={(event) => setQuery(event.target.value)} rows={7} placeholder="写下目标人群、平台、素材和你想判断的问题。" />
        </label>
        <div className="actions command-row">
          <button className="primary" disabled={status === "running" || !query.trim()}>
            {status === "running" ? "运行中" : "开始分析"}
          </button>
          <button type="button" onClick={startNew}>清空</button>
        </div>
      </form>

      <aside className="context-rail">
        <section className="studio-panel status-panel">
          <div className="panel-head">
            <div>
              <p className="section-kicker">状态</p>
              <h2>任务进度</h2>
            </div>
            <StatusBadge status={status} />
          </div>
          <RunTimeline status={status} stages={run?.stages} />
          {error && <ErrorNotice message={error} onRetry={() => void runWorkflow()} />}
          {run ? (
            <div className="result-list">
              <div><span>路径</span><strong>{run.route || "等待中"}</strong></div>
              <div><span>报告</span><strong>{run.report_path || "等待中"}</strong></div>
              <div><span>记录</span><strong>{run.trace_path || "等待中"}</strong></div>
              <button type="button" onClick={onOpenReports}>查看报告</button>
            </div>
          ) : (
            <p className="muted">尚未运行。默认只走本地。</p>
          )}
        </section>

        <section className="studio-panel mini-context">
          <p className="section-kicker">当前</p>
          <dl>
            <div><dt>任务</dt><dd>{taskType}</dd></div>
            <div><dt>输出</dt><dd>{outputTarget}</dd></div>
            <div><dt>来源</dt><dd>{sourceContext}</dd></div>
          </dl>
        </section>
      </aside>
    </section>
  );
}
