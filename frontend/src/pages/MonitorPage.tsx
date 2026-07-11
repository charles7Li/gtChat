import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { ErrorNotice } from "../components/ErrorNotice";
import { StatusBadge } from "../components/StatusBadge";
import type { MonitorJob } from "../types";

const initialJob: MonitorJob = {
  name: "宠物热点检查",
  enabled: true,
  platforms: ["douyin_hot_board"],
  keywords: ["pet"],
  interval_seconds: 3600,
  allow_live: false,
  output_dir: "outputs/hotspot",
  rule: { min_heat_score: 80, min_growth_rate: 0, min_rank: 100, min_engagement: 0, required_sources: [] },
};

export function MonitorPage() {
  const [job, setJob] = useState<MonitorJob>(initialJob);
  const [jobs, setJobs] = useState<MonitorJob[]>([]);
  const [savedId, setSavedId] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [digest, setDigest] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const saved = await api.saveJob(job);
      setSavedId(saved.job_id || "");
      setJobs(await api.listJobs());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function runOnce() {
    if (!savedId) return;
    setBusy(true);
    setError("");
    try {
      setResult(await api.runJob(savedId));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "运行失败");
    } finally {
      setBusy(false);
    }
  }

  async function refreshDigest() {
    setBusy(true);
    setError("");
    try {
      setDigest(await api.digest());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "摘要刷新失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void api.listJobs().then(setJobs).catch(() => setJobs([]));
  }, []);

  return (
    <section className="monitor-layout">
      <form className="studio-panel monitor-form" onSubmit={save}>
        <div className="panel-intro compact">
          <p className="section-kicker">配置</p>
          <h2>本地信号检查</h2>
        </div>
        <div className="field-group">
          <label>任务名<input value={job.name} onChange={(event) => setJob({ ...job, name: event.target.value })} /></label>
          <label>间隔秒数<input type="number" min="60" value={job.interval_seconds} onChange={(event) => setJob({ ...job, interval_seconds: Number(event.target.value) })} /></label>
        </div>
        <div className="field-group">
          <label>平台<input value={job.platforms.join(",")} onChange={(event) => setJob({ ...job, platforms: split(event.target.value) })} /></label>
          <label>关键词<input value={job.keywords.join(",")} onChange={(event) => setJob({ ...job, keywords: split(event.target.value) })} /></label>
        </div>
        <div className="threshold-grid">
          <label>热度<input type="number" value={job.rule.min_heat_score || 0} onChange={(event) => setJob({ ...job, rule: { ...job.rule, min_heat_score: Number(event.target.value) } })} /></label>
          <label>增长<input type="number" step="0.01" value={job.rule.min_growth_rate || 0} onChange={(event) => setJob({ ...job, rule: { ...job.rule, min_growth_rate: Number(event.target.value) } })} /></label>
          <label>排名<input type="number" min="1" value={job.rule.min_rank || 1} onChange={(event) => setJob({ ...job, rule: { ...job.rule, min_rank: Number(event.target.value) } })} /></label>
          <label>互动<input type="number" min="0" value={job.rule.min_engagement || 0} onChange={(event) => setJob({ ...job, rule: { ...job.rule, min_engagement: Number(event.target.value) } })} /></label>
        </div>
        <label>信号路径<input value={job.signals_path || ""} onChange={(event) => setJob({ ...job, signals_path: event.target.value || undefined })} /></label>
        <label className="toggle-line live-toggle">
          <input type="checkbox" checked={job.allow_live} onChange={(event) => setJob({ ...job, allow_live: event.target.checked })} />
          <span>
            允许联网
            <small>{job.allow_live ? "可能访问外部服务" : "默认本地检查"}</small>
          </span>
        </label>
        <div className="actions command-row">
          <button className="primary" disabled={busy}>保存</button>
          <button type="button" disabled={busy || !savedId} onClick={() => void runOnce()}>运行一次</button>
        </div>
      </form>

      <section className="studio-panel monitor-results">
        <div className="panel-head">
          <div>
            <p className="section-kicker">最近</p>
            <h2>{savedId || "未保存"}</h2>
          </div>
          <StatusBadge status={busy ? "running" : savedId ? "success" : "pending"} />
        </div>
        {error && <ErrorNotice message={error} />}
        <div className="actions"><button type="button" disabled={busy} onClick={() => void refreshDigest()}>刷新摘要</button></div>
        <pre className="json-preview">{JSON.stringify(result || { next_step: "先保存，再运行一次。" }, null, 2)}</pre>
        {digest && <pre className="json-preview">{JSON.stringify(digest, null, 2)}</pre>}
      </section>

      <section className="studio-panel saved-jobs">
        <div className="panel-head"><h2>已保存</h2><span className="env-pill">{jobs.length}</span></div>
        <div className="report-list">
          {jobs.map((saved) => (
            <button key={saved.job_id} className={savedId === saved.job_id ? "report-row active" : "report-row"} onClick={() => setSavedId(saved.job_id || "")}>
              <span><strong>{saved.name}</strong><small>{saved.platforms.join(", ")} · {saved.keywords.join(", ")}</small></span>
              <span className="env-pill">{saved.allow_live ? "联网" : "本地"}</span>
            </button>
          ))}
        </div>
      </section>
    </section>
  );
}

function split(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}
