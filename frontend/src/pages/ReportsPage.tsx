import { useEffect, useState } from "react";
import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { ReportPreview } from "../components/ReportPreview";
import { StatusBadge } from "../components/StatusBadge";
import type { ChatRun } from "../types";

export function ReportsPage() {
  const [reports, setReports] = useState<ChatRun[]>([]);
  const [selected, setSelected] = useState<ChatRun | null>(null);
  const [artifact, setArtifact] = useState<Record<string, unknown> | null>(null);
  const [artifactName, setArtifactName] = useState<"trace" | "manifest" | "evidence">("trace");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const items = await api.listReports();
      setReports(items);
      const target = items.find((item) => item.run_id === selected?.run_id) || items[0];
      if (target) await preview(target.run_id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "报告加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function preview(runId: string) {
    setError("");
    try {
      const report = await api.getReport(runId);
      setSelected(report);
      setArtifact(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "报告打开失败");
    }
  }

  async function loadArtifact(name: "trace" | "manifest" | "evidence") {
    if (!selected) return;
    setArtifactName(name);
    setError("");
    try {
      setArtifact(await api.getArtifact(selected.run_id, name));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "证据加载失败");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <section className="reports-layout">
      <aside className="report-index">
        <div className="panel-head">
          <div>
            <p className="section-kicker">列表</p>
            <h2>最近报告</h2>
          </div>
          <button type="button" onClick={() => void load()} disabled={loading}>刷新</button>
        </div>
        {error && <ErrorNotice message={error} onRetry={load} />}
        {!loading && !reports.length && <EmptyState title="暂无报告" action="先运行一次简报。" />}
        <div className="report-list">
          {reports.map((report) => (
            <button key={report.run_id} className={selected?.run_id === report.run_id ? "report-row active" : "report-row"} onClick={() => void preview(report.run_id)}>
              <span>
                <strong>{report.title || report.query || "未命名报告"}</strong>
                <small>{briefLabel(report.query) || routeLabel(report.route)}</small>
                <small>{new Date(report.created_at).toLocaleString()} · {report.warnings?.length || 0} 条提醒</small>
              </span>
              <StatusBadge status={report.status} />
            </button>
          ))}
        </div>
      </aside>

      <section className="reader-pane">
        <div className="reader-toolbar">
          <div>
            <p className="section-kicker">阅读</p>
            <h2>{selected?.title || selected?.query || "选择一份报告"}</h2>
            {selected && <p className="reader-meta">{routeLabel(selected.route)} · {new Date(selected.created_at).toLocaleString()}</p>}
          </div>
          {selected?.run_id && <a className="button-link" href={`/api/reports/${encodeURIComponent(selected.run_id)}/download`}>下载 MD</a>}
        </div>
        {selected?.warnings?.length ? (
          <details className="report-warnings">
            <summary>{selected.warnings.length} 条运行提醒</summary>
            <ul>{selected.warnings.map((warning, index) => <li key={index}>{warningText(warning)}</li>)}</ul>
          </details>
        ) : null}
        <ReportPreview markdown={selected?.markdown || ""} />
      </section>

      <EvidenceDrawer
        selectedName={artifactName}
        artifact={artifact}
        tracePath={selected?.trace_path}
        manifestPath={selected?.manifest_path}
        evidencePath={selected?.evidence_path}
        onLoad={loadArtifact}
      />
    </section>
  );
}

function routeLabel(route: string): string {
  return ({
    trend_report_path: "趋势报告",
    imitation_plan_path: "仿拍方案",
    reference_video_imitation_path: "参考视频分析",
    full_pipeline_path: "联网全流程",
    commercial_data_analysis_path: "商业数据分析",
  } as Record<string, string>)[route] || route || "未知路线";
}

function warningText(warning: Record<string, unknown>): string {
  const message = warning.message || warning.detail || warning.code;
  return typeof message === "string" ? message : JSON.stringify(warning);
}

function briefLabel(query?: string): string {
  if (!query) return "";
  const brief = query.split("简报：").pop()?.trim() || query;
  if (/^[?\s]+$/.test(brief)) return "历史任务";
  return brief.length > 48 ? `${brief.slice(0, 48)}…` : brief;
}
