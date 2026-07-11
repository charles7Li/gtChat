export function ReportPreview({ markdown }: { markdown: string }) {
  if (!markdown.trim()) {
    return (
      <div className="report-preview empty-preview">
        <p>选择一份报告。</p>
      </div>
    );
  }
  return <article className="report-preview">{markdown}</article>;
}
