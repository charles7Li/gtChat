import { useState } from "react";
import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { FileDropzone } from "../components/FileDropzone";
import { StatusBadge } from "../components/StatusBadge";
import type { UploadAsset } from "../types";

export function UploadPage({ onOpenReports }: { onOpenReports: () => void }) {
  const [assets, setAssets] = useState<UploadAsset[]>([]);
  const [processResult, setProcessResult] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload(files: FileList) {
    const accepted = Array.from(files).filter(isAccepted);
    if (accepted.length !== files.length) {
      setError("文件类型暂不支持。");
    }
    if (!accepted.length) return;
    setBusy(true);
    if (accepted.length === files.length) setError("");
    try {
      const uploaded = await Promise.all(accepted.map((file) => api.upload(file)));
      setAssets((current) => [...uploaded, ...current]);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  async function process(asset: UploadAsset) {
    setBusy(true);
    setError("");
    setProcessResult(null);
    try {
      if (asset.file_type === "video") setProcessResult(await api.analyzeVideo(asset.path));
      if (asset.file_type === "csv" || asset.file_type === "json") setProcessResult(await api.importFile(asset.path));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "处理失败");
    } finally {
      setBusy(false);
    }
  }

  const briefPath = getOutputPath(processResult);

  return (
    <section className="upload-layout">
      <div className="intake-panel">
        <div className="panel-intro">
          <p className="section-kicker">导入</p>
          <h2>添加素材</h2>
        </div>
        <FileDropzone disabled={busy} onFiles={upload} />
        {error && <ErrorNotice message={error} />}
      </div>

      <section className="studio-panel">
        <div className="panel-head">
          <div>
            <p className="section-kicker">队列</p>
            <h2>已上传</h2>
          </div>
          <StatusBadge status={busy ? "running" : assets.length ? "success" : "pending"} />
        </div>
        <div className="asset-list">
          {assets.map((asset) => (
            <div className="asset-row" key={asset.asset_id}>
              <div>
                <strong>{asset.filename}</strong>
                <span>{asset.file_type} · {asset.path}</span>
              </div>
              <button disabled={busy || asset.file_type === "image" || asset.file_type === "other"} onClick={() => process(asset)}>
                处理
              </button>
            </div>
          ))}
          {!assets.length && <EmptyState title="暂无素材" action="拖入文件开始。" />}
        </div>
      </section>

      <section className="studio-panel result-panel">
        <div className="panel-head">
          <div>
            <p className="section-kicker">结果</p>
            <h2>最新输出</h2>
          </div>
          <button type="button" onClick={onOpenReports}>报告</button>
        </div>
        {processResult ? (
          <>
            {briefPath && <a className="artifact-link" href={`/api/files?path=${encodeURIComponent(briefPath)}`}>打开分析文件</a>}
            <pre className="json-preview">{JSON.stringify(processResult, null, 2)}</pre>
          </>
        ) : (
          <p className="muted">处理结果会显示在这里。</p>
        )}
      </section>
    </section>
  );
}

function getOutputPath(result: Record<string, unknown> | null): string {
  const meta = result?._analysis_meta;
  if (!meta || typeof meta !== "object" || !("output_path" in meta)) return "";
  const outputPath = meta.output_path;
  return typeof outputPath === "string" ? outputPath : "";
}

function isAccepted(file: File): boolean {
  const suffix = file.name.toLowerCase().split(".").pop() || "";
  return ["mp4", "mov", "m4v", "avi", "mkv", "webm", "png", "jpg", "jpeg", "gif", "webp", "csv", "json"].includes(suffix);
}
