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
  return (
    <aside className="evidence-drawer" aria-label="证据">
      <div className="drawer-head">
        <span className="section-kicker">证据</span>
        <strong>来源</strong>
      </div>
      <div className="evidence-tabs" role="tablist" aria-label="证据文件">
        {(Object.keys(labels) as Array<"trace" | "manifest" | "evidence">).map((name) => (
          <button key={name} type="button" className={selectedName === name ? "active" : ""} onClick={() => onLoad(name)}>
            {labels[name]}
          </button>
        ))}
      </div>
      <dl className="path-list">
        <div><dt>记录</dt><dd>{tracePath || "暂无"}</dd></div>
        <div><dt>清单</dt><dd>{manifestPath || "暂无"}</dd></div>
        <div><dt>证据</dt><dd>{evidencePath || "暂无"}</dd></div>
      </dl>
      <pre className="json-preview evidence-preview">{artifact ? JSON.stringify(artifact, null, 2) : "选择一项查看。"}</pre>
    </aside>
  );
}
