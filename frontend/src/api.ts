import type { ChatRun, MonitorJob, UploadAsset } from "./types";

export type Platform = "xiaohongshu" | "douyin";
export type LoginState = {
  platform: Platform;
  status: "saved" | "auth_required" | "invalid";
  cookie_count: number;
  updated_at: string | null;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const adminToken = import.meta.env.VITE_MOCHI_ADMIN_TOKEN;
  if (adminToken) headers.set("x-mochi-admin-token", adminToken);
  const response = await fetch(url, { ...init, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.detail;
    const message = typeof detail === "string"
      ? detail
      : detail?.message || `${response.status} ${response.statusText}`;
    throw new ApiError(message, response.status, detail?.code);
  }
  if (response.status === 204) return undefined as T;
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
  getChatRun(runId: string) {
    return request<ChatRun>(`/api/chat/runs/${encodeURIComponent(runId)}`);
  },
  listChatRuns() {
    return request<ChatRun[]>("/api/chat/runs");
  },
  cancelChatRun(runId: string) {
    return request<ChatRun>(`/api/chat/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
  },
  retryChatRun(runId: string) {
    return request<ChatRun>(`/api/chat/runs/${encodeURIComponent(runId)}/retry`, { method: "POST" });
  },
  upload(file: File) {
    return request<UploadAsset>(`/api/uploads?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      headers: { "content-type": file.type || "application/octet-stream" },
      body: file,
    });
  },
  listUploads() {
    return request<UploadAsset[]>("/api/uploads");
  },
  processUpload(assetId: string) {
    return request<UploadAsset>(`/api/uploads/${encodeURIComponent(assetId)}/process`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
    });
  },
  deleteUpload(assetId: string) {
    return request<void>(`/api/uploads/${encodeURIComponent(assetId)}`, { method: "DELETE" });
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
  deleteJob(jobId: string) {
    return request<void>(`/api/monitor/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" });
  },
  digest() {
    return request<Record<string, unknown>>("/api/monitor/digest");
  },
  authStatus() {
    return request<Record<Platform, LoginState>>("/api/auth/status");
  },
  startAuthLogin(platform: Platform) {
    return request<{ platform: Platform; session_id: string; status: "started" | "running" }>(`/api/auth/${platform}/login`, { method: "POST" });
  },
  completeAuthLogin(sessionId: string) {
    return request<{ session_id: string; platform: Platform; status: string }>(`/api/auth/sessions/${encodeURIComponent(sessionId)}/complete`, { method: "POST" });
  },
  getAuthSession(sessionId: string) {
    return request<{ session_id: string; platform: Platform; status: string }>(`/api/auth/sessions/${encodeURIComponent(sessionId)}`);
  },
  saveAuthState(platform: Platform, cookies: Record<string, unknown>[]) {
    return request<LoginState>(`/api/auth/${platform}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ cookies }),
    });
  },
};
