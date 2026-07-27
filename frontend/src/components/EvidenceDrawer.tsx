type EvidenceDrawerProps = {
  selectedName: "trace" | "manifest" | "evidence";
  artifact: Record<string, unknown> | null;
  tracePath?: string;
  manifestPath?: string;
  evidencePath?: string;
  onLoad: (name: "trace" | "manifest" | "evidence") => void;
};

const labels: Record<"trace" | "manifest" | "evidence", string> = {
  trace: "记录",
  manifest: "清单",
  evidence: "证据",
};

export function EvidenceDrawer({ selectedName, artifact, tracePath, manifestPath, evidencePath, onLoad }: EvidenceDrawerProps) {
  const available = { trace: Boolean(tracePath), manifest: Boolean(manifestPath), evidence: Boolean(evidencePath) };
  return (
    <aside className="evidence-drawer" aria-label="证据">
      <div className="drawer-head">
        <span className="section-kicker">证据</span>
        <strong>来源</strong>
      </div>
      <div className="evidence-tabs" role="tablist" aria-label="证据文件">
        {(Object.keys(labels) as Array<"trace" | "manifest" | "evidence">).map((name) => (
          <button key={name} type="button" disabled={!available[name]} className={selectedName === name ? "active" : ""} onClick={() => onLoad(name)}>
            {labels[name]}
          </button>
        ))}
      </div>
      <dl className="path-list">
        <div><dt>运行记录</dt><dd>{available.trace ? "可查看" : "未生成"}</dd></div>
        <div><dt>产物清单</dt><dd>{available.manifest ? "可查看" : "未生成"}</dd></div>
        <div><dt>证据包</dt><dd>{available.evidence ? "可查看" : "未生成"}</dd></div>
      </dl>
      <pre className="json-preview evidence-preview">{artifact ? JSON.stringify(artifact, null, 2) : "选择一项查看。"}</pre>
    </aside>
  );
}
