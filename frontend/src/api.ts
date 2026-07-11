import type { ChatRun, MonitorJob, UploadAsset } from "./types";

export type Platform = "xiaohongshu" | "douyin";
export type LoginState = {
  platform: Platform;
  status: "saved" | "auth_required" | "invalid";
  cookie_count: number;
  updated_at: string | null;
};

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  runChat(query: string, allowLive: boolean) {
    return request<ChatRun>("/api/chat/runs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, allow_live: allowLive }),
    });
  },
  upload(file: File) {
    return request<UploadAsset>(`/api/uploads?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      headers: { "content-type": file.type || "application/octet-stream" },
      body: file,
    });
  },
  analyzeVideo(path: string) {
    return request<Record<string, unknown>>("/api/video/analyze", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ path }),
    });
  },
  importFile(path: string) {
    return request<Record<string, unknown>>("/api/imports", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source: "chanmama", path }),
    });
  },
  listReports() {
    return request<ChatRun[]>("/api/reports");
  },
  getReport(runId: string) {
    return request<ChatRun>(`/api/reports/${encodeURIComponent(runId)}`);
  },
  getArtifact(runId: string, artifact: "trace" | "manifest" | "evidence") {
    return request<Record<string, unknown>>(`/api/reports/${encodeURIComponent(runId)}/artifacts/${artifact}`);
  },
  listJobs() {
    return request<MonitorJob[]>("/api/monitor/jobs");
  },
  saveJob(job: MonitorJob) {
    return request<MonitorJob>("/api/monitor/jobs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(job),
    });
  },
  runJob(jobId: string) {
    return request<Record<string, unknown>>(`/api/monitor/jobs/${encodeURIComponent(jobId)}/run-once`, { method: "POST" });
  },
  digest() {
    return request<Record<string, unknown>>("/api/monitor/digest");
  },
  authStatus() {
    return request<Record<Platform, LoginState>>("/api/auth/status");
  },
  saveAuthState(platform: Platform, cookies: Record<string, unknown>[]) {
    return request<LoginState>(`/api/auth/${platform}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ cookies }),
    });
  },
};
