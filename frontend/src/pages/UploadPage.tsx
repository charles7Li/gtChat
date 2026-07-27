import { useEffect, useState } from "react";
import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { FileDropzone } from "../components/FileDropzone";
import { StatusBadge } from "../components/StatusBadge";
import type { UploadAsset } from "../types";

export function UploadPage({ onOpenReports }: { onOpenReports: () => void }) {
  const [assets, setAssets] = useState<UploadAsset[]>([]);
  const [processResult, setProcessResult] = useState<Record<string, unknown> | null>(null);
  const [busyId, setBusyId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    try {
      setAssets(await api.listUploads());
      setError("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "素材加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function upload(files: FileList) {
    const accepted = Array.from(files).filter(isAccepted);
    if (accepted.length !== files.length) setError("部分文件类型暂不支持，已跳过。");
    if (!accepted.length) return;
    setBusyId("upload");
    try {
      const uploaded = await Promise.all(accepted.map((file) => api.upload(file)));
      setAssets((current) => [...uploaded, ...current]);
      if (accepted.length === files.length) setError("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "上传失败");
    } finally {
      setBusyId("");
    }
  }

  async function process(asset: UploadAsset) {
    setBusyId(asset.asset_id);
    setError("");
    setProcessResult(null);
    try {
      const updated = await api.processUpload(asset.asset_id);
      setProcessResult(updated.result || null);
      setAssets((current) => current.map((item) => item.asset_id === updated.asset_id ? updated : item));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "处理失败");
      await load();
    } finally {
      setBusyId("");
    }
  }

  async function remove(asset: UploadAsset) {
    if (!window.confirm(`删除素材“${asset.filename}”？`)) return;
    setBusyId(asset.asset_id);
    try {
      await api.deleteUpload(asset.asset_id);
      setAssets((current) => current.filter((item) => item.asset_id !== asset.asset_id));
      setProcessResult(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "删除失败");
    } finally {
      setBusyId("");
    }
  }

  return (
    <section className="upload-layout">
      <div className="intake-panel">
        <div className="panel-intro">
          <p className="section-kicker">导入</p>
          <h2>添加素材</h2>
          <p>支持视频、图片、CSV 和 JSON。文件只保存在本地工作区，除非任务明确允许联网。</p>
        </div>
        <FileDropzone disabled={Boolean(busyId)} onFiles={upload} />
        {error && <ErrorNotice message={error} onRetry={load} />}
      </div>

      <section className="studio-panel">
        <div className="panel-head">
          <div>
            <p className="section-kicker">素材库</p>
            <h2>已上传</h2>
          </div>
          <StatusBadge status={busyId || loading ? "running" : assets.length ? "success" : "pending"} />
        </div>
        <div className="asset-list">
          {assets.map((asset) => (
            <div className="asset-row" key={asset.asset_id}>
              <div>
                <strong>{asset.filename}</strong>
                <span>{assetLabel(asset.file_type)} · {formatBytes(asset.size)} · {formatTime(asset.created_at)}</span>
                {asset.error && <span className="asset-error">{asset.error}</span>}
              </div>
              <div className="asset-actions">
                <span className={`asset-status asset-status-${asset.status}`}>{statusLabel(asset.status)}</span>
                <button disabled={Boolean(busyId) || asset.file_type === "image" || asset.file_type === "other"} onClick={() => void process(asset)}>
                  {busyId === asset.asset_id ? "处理中" : asset.status === "completed" ? "重新处理" : "处理"}
                </button>
                <button className="danger-button" disabled={Boolean(busyId)} onClick={() => void remove(asset)}>删除</button>
              </div>
            </div>
          ))}
          {!loading && !assets.length && <EmptyState title="暂无素材" action="拖入一段参考视频或一份 CSV，完成后可继续创建分析任务。" />}
        </div>
      </section>

      <section className="studio-panel result-panel">
        <div className="panel-head">
          <div>
            <p className="section-kicker">处理结果</p>
            <h2>最新输出</h2>
          </div>
          <button type="button" onClick={onOpenReports}>打开报告库</button>
        </div>
        {processResult ? <ProcessSummary result={processResult} /> : <p className="muted">选择视频或数据文件进行处理，结果会保留在对应素材记录中。</p>}
      </section>
    </section>
  );
}

function ProcessSummary({ result }: { result: Record<string, unknown> }) {
  const recordCount = typeof result.record_count === "number" ? result.record_count : null;
  const hasAnalysis = Boolean(result._analysis_meta && typeof result._analysis_meta === "object");
  return (
    <div className="process-summary">
      <strong>处理完成</strong>
      {recordCount !== null && <p>已识别 {recordCount} 条记录，可以在对话任务中继续分析。</p>}
      {hasAnalysis && <p>参考视频已完成结构拆解，相关分析产物已写入本地报告目录。</p>}
      {recordCount === null && !hasAnalysis && <p>素材处理成功，可继续创建分析任务。</p>}
    </div>
  );
}

function isAccepted(file: File): boolean {
  const suffix = file.name.toLowerCase().split(".").pop() || "";
  return ["mp4", "mov", "m4v", "avi", "mkv", "webm", "png", "jpg", "jpeg", "gif", "webp", "csv", "json"].includes(suffix);
}

function formatBytes(size: number): string {
  if (!size) return "大小未知";
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(value: string): string {
  const time = new Date(value);
  return Number.isNaN(time.getTime()) ? "时间未知" : time.toLocaleString();
}

function assetLabel(type: UploadAsset["file_type"]): string {
  return ({ video: "视频", image: "图片", csv: "CSV 数据", json: "JSON 数据", other: "文件" })[type];
}

function statusLabel(status: UploadAsset["status"]): string {
  return ({ uploaded: "待处理", processing: "处理中", completed: "已完成", failed: "处理失败" })[status];
}
