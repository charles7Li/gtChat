export function ReportPreview({ markdown }: { markdown: string }) {
  if (!markdown) return <p className="muted">选择一份报告后预览 Markdown 正文。</p>;
  return <pre className="report-preview">{markdown}</pre>;
}
