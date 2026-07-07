import { useEffect, useState } from "react";
import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
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
      setReports(await api.listReports());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Failed to load reports");
    } finally {
      setLoading(false);
    }
  }

  async function preview(runId: string) {
    setError("");
    try {
      setSelected(await api.getReport(runId));
      setArtifact(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Failed to load report");
    }
  }

  async function loadArtifact(name: "trace" | "manifest" | "evidence") {
    if (!selected) return;
    setArtifactName(name);
    setError("");
    try {
      setArtifact(await api.getArtifact(selected.run_id, name));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Failed to load artifact");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <section className="content-grid two-col wide-left">
      <div className="panel">
        <div className="panel-head">
          <h2>Reports</h2>
          <button onClick={() => void load()} disabled={loading}>Refresh</button>
        </div>
        {error && <ErrorNotice message={error} onRetry={load} />}
        {!loading && !reports.length && <EmptyState title="还没有报告" action="先在 Agent Chat 运行一次 workflow。" />}
        <div className="report-list">
          {reports.map((report) => (
            <button key={report.run_id} className="report-row" onClick={() => void preview(report.run_id)}>
              <span>
                <strong>{report.run_id}</strong>
                <small>
                  {report.route} · {new Date(report.created_at).toLocaleString()} · {report.warnings?.length || 0} warnings
                </small>
              </span>
              <StatusBadge status={report.status} />
            </button>
          ))}
        </div>
      </div>
      <div className="panel">
        <div className="panel-head">
          <h2>Preview</h2>
          {selected?.run_id && <a href={`/api/reports/${encodeURIComponent(selected.run_id)}/download`}>Download</a>}
        </div>
        <ReportPreview markdown={selected?.markdown || ""} />
        {selected && (
          <div className="debug-links">
            <div className="actions">
              <button onClick={() => void loadArtifact("trace")}>Trace</button>
              <button onClick={() => void loadArtifact("manifest")}>Manifest</button>
              <button onClick={() => void loadArtifact("evidence")}>Evidence</button>
            </div>
            <span>Trace: {selected.trace_path || "missing"}</span>
            <span>Manifest: {selected.manifest_path || "missing"}</span>
            {artifact && <pre className="json-preview">{artifactName}: {JSON.stringify(artifact, null, 2)}</pre>}
          </div>
        )}
      </div>
    </section>
  );
}
