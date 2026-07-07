import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { ErrorNotice } from "../components/ErrorNotice";
import type { MonitorJob } from "../types";

const initialJob: MonitorJob = {
  name: "Pet hotspot dry-run",
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
      setError(exc instanceof Error ? exc.message : "Save failed");
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
      setError(exc instanceof Error ? exc.message : "Run failed");
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
      setError(exc instanceof Error ? exc.message : "Digest failed");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void api.listJobs().then(setJobs).catch(() => setJobs([]));
  }, []);

  return (
    <section className="content-grid two-col">
      <form className="panel" onSubmit={save}>
        <label>任务名称<input value={job.name} onChange={(event) => setJob({ ...job, name: event.target.value })} /></label>
        <label>平台<input value={job.platforms.join(",")} onChange={(event) => setJob({ ...job, platforms: split(event.target.value) })} /></label>
        <label>关键词<input value={job.keywords.join(",")} onChange={(event) => setJob({ ...job, keywords: split(event.target.value) })} /></label>
        <label>频率秒数<input type="number" min="60" value={job.interval_seconds} onChange={(event) => setJob({ ...job, interval_seconds: Number(event.target.value) })} /></label>
        <label>热度阈值<input type="number" value={job.rule.min_heat_score || 0} onChange={(event) => setJob({ ...job, rule: { ...job.rule, min_heat_score: Number(event.target.value) } })} /></label>
        <label>增长率阈值<input type="number" step="0.01" value={job.rule.min_growth_rate || 0} onChange={(event) => setJob({ ...job, rule: { ...job.rule, min_growth_rate: Number(event.target.value) } })} /></label>
        <label>排名阈值<input type="number" min="1" value={job.rule.min_rank || 1} onChange={(event) => setJob({ ...job, rule: { ...job.rule, min_rank: Number(event.target.value) } })} /></label>
        <label>互动量阈值<input type="number" min="0" value={job.rule.min_engagement || 0} onChange={(event) => setJob({ ...job, rule: { ...job.rule, min_engagement: Number(event.target.value) } })} /></label>
        <label>Signals path<input value={job.signals_path || ""} onChange={(event) => setJob({ ...job, signals_path: event.target.value || undefined })} /></label>
        <label className="switch">
          <input type="checkbox" checked={job.allow_live} onChange={(event) => setJob({ ...job, allow_live: event.target.checked })} />
          允许 live 外部调用
        </label>
        <p className="hint">
          {job.allow_live
            ? "Live 已开启：后续接入真实配置时可能触发抖音、Webhook 或其他外部服务。"
            : "Live 已关闭：手动运行使用本地 signals 文件；没有 signals 文件则执行空 dry-run。"}
        </p>
        <div className="actions">
          <button className="primary" disabled={busy}>Save job</button>
          <button type="button" disabled={busy || !savedId} onClick={() => void runOnce()}>Run once</button>
        </div>
      </form>
      <section className="panel">
        <div className="panel-head">
          <h2>Last run</h2>
          <span className="env-pill">{savedId || "unsaved"}</span>
        </div>
        <div className="actions">
          <button type="button" disabled={busy} onClick={() => void refreshDigest()}>Refresh digest</button>
        </div>
        {error && <ErrorNotice message={error} />}
        <pre className="json-preview">{JSON.stringify(result || { next_step: "Save a job, then run once." }, null, 2)}</pre>
        {digest && <pre className="json-preview">{JSON.stringify(digest, null, 2)}</pre>}
        <div className="asset-list">
          {jobs.map((saved) => (
            <button key={saved.job_id} className="report-row" onClick={() => setSavedId(saved.job_id || "")}>
              <span>
                <strong>{saved.name}</strong>
                <small>{saved.platforms.join(", ")} · {saved.keywords.join(", ")}</small>
              </span>
              <span className="env-pill">{saved.allow_live ? "live" : "dry-run"}</span>
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
