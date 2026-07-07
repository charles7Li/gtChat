import { useState } from "react";
import { api } from "../api";
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
      setError("Unsupported file type. Accept video, image, CSV, or JSON.");
    }
    if (!accepted.length) return;
    setBusy(true);
    if (accepted.length === files.length) setError("");
    try {
      const uploaded = await Promise.all(accepted.map((file) => api.upload(file)));
      setAssets((current) => [...uploaded, ...current]);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Upload failed");
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
      setError(exc instanceof Error ? exc.message : "Process failed");
    } finally {
      setBusy(false);
    }
  }

  const briefPath = getOutputPath(processResult);

  return (
    <section className="content-grid">
      <div className="panel">
        <FileDropzone disabled={busy} onFiles={upload} />
        {error && <ErrorNotice message={error} />}
      </div>
      <div className="panel">
        <div className="panel-head">
          <h2>Uploaded assets</h2>
          <StatusBadge status={busy ? "running" : "success"} />
        </div>
        <div className="asset-list">
          {assets.map((asset) => (
            <div className="row" key={asset.asset_id}>
              <div>
                <strong>{asset.filename}</strong>
                <span>{asset.file_type} · {asset.path}</span>
              </div>
              <button disabled={busy || asset.file_type === "image" || asset.file_type === "other"} onClick={() => process(asset)}>
                Process
              </button>
            </div>
          ))}
          {!assets.length && <p className="muted">上传素材后，视频可进入本地分析，CSV/JSON 可进入导入流程。</p>}
        </div>
        {processResult && (
          <>
            {briefPath && (
              <a href={`/api/files?path=${encodeURIComponent(briefPath)}`}>
                Open video_analysis_brief.json
              </a>
            )}
            <pre className="json-preview">{JSON.stringify(processResult, null, 2)}</pre>
          </>
        )}
        <button onClick={onOpenReports}>Open reports</button>
      </div>
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
