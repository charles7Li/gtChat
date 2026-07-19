import Taro from "@tarojs/taro";
import type { MobileJob, MobileReport, Session, UploadAsset } from "./types";

const ACCESS_KEY = "mochi-access-token";
const REFRESH_KEY = "mochi-refresh-token";

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  data?: unknown;
  headers?: Record<string, string>;
  auth?: boolean;
  authRetried?: boolean;
};

let refreshPromise: Promise<boolean> | null = null;

export class ApiError extends Error {
  code: string;
  retryable: boolean;

  constructor(code: string, message: string, retryable = false) {
    super(message);
    this.code = code;
    this.retryable = retryable;
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = Taro.getStorageSync<string>(ACCESS_KEY);
  const response = await Taro.request({
    url: `${MOCHI_API_BASE}${path}`,
    method: options.method || "GET",
    data: options.data,
    header: {
      "content-type": "application/json",
      ...(options.auth !== false && token ? { authorization: `Bearer ${token}` } : {}),
      ...options.headers
    }
  });
  if (response.statusCode >= 200 && response.statusCode < 300) return response.data as T;
  if (response.statusCode === 401 && options.auth !== false && !options.authRetried) {
    if (await refreshSession()) {
      return request<T>(path, { ...options, authRetried: true });
    }
  }
  const detail = (response.data as { detail?: { code?: string; message?: string; retryable?: boolean } })?.detail;
  throw new ApiError(detail?.code || `HTTP_${response.statusCode}`, detail?.message || "请求失败", detail?.retryable);
}

export async function ensureSession(): Promise<void> {
  if (Taro.getStorageSync(ACCESS_KEY)) return;
  const login = await Taro.login();
  const session = await request<Session>("/api/v1/mobile/session/wechat", {
    method: "POST",
    auth: false,
    data: { code: login.code }
  });
  Taro.setStorageSync(ACCESS_KEY, session.access_token);
  Taro.setStorageSync(REFRESH_KEY, session.refresh_token);
}

async function refreshSession(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const refreshToken = Taro.getStorageSync<string>(REFRESH_KEY);
    if (refreshToken) {
      const response = await Taro.request<Session>({
        url: `${MOCHI_API_BASE}/api/v1/mobile/session/refresh`,
        method: "POST",
        data: { refresh_token: refreshToken },
        header: { "content-type": "application/json" }
      });
      if (response.statusCode >= 200 && response.statusCode < 300) {
        Taro.setStorageSync(ACCESS_KEY, response.data.access_token);
        Taro.setStorageSync(REFRESH_KEY, response.data.refresh_token);
        return true;
      }
    }
    Taro.removeStorageSync(ACCESS_KEY);
    Taro.removeStorageSync(REFRESH_KEY);
    try {
      await ensureSession();
      return true;
    } catch {
      return false;
    }
  })().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

export const api = {
  async uploadLocalFile(file: { path: string; name: string; size: number; type?: string }) {
    await ensureSession();
    const asset = await request<UploadAsset & {
      upload_url: string;
      upload_headers?: Record<string, string>;
      direct_upload?: boolean;
    }>("/api/v1/mobile/uploads/init", {
      method: "POST",
      data: { filename: file.name, content_type: file.type || contentType(file.name), size: file.size }
    });
    const data = await readBinary(file.path);
    await uploadBinary(asset.upload_url, data, {
      "content-type": file.type || contentType(file.name),
      ...(asset.upload_headers || {})
    }, Boolean(asset.direct_upload));
    return request<UploadAsset>(`/api/v1/mobile/uploads/${asset.id}/complete`, { method: "POST" });
  },
  async listJobs() {
    await ensureSession();
    return request<MobileJob[]>("/api/v1/mobile/jobs");
  },
  async getJob(jobId: string) {
    await ensureSession();
    return request<MobileJob>(`/api/v1/mobile/jobs/${jobId}`);
  },
  async createJob(input: { query: string; route: string; asset_ids?: string[] }) {
    await ensureSession();
    return request<MobileJob>("/api/v1/mobile/jobs", {
      method: "POST",
      headers: { "Idempotency-Key": `${Date.now()}-${Math.random().toString(16).slice(2)}` },
      data: { ...input, allow_live: false }
    });
  },
  async cancelJob(jobId: string) {
    return request<MobileJob>(`/api/v1/mobile/jobs/${jobId}/cancel`, { method: "POST" });
  },
  async retryJob(jobId: string) {
    return request<MobileJob>(`/api/v1/mobile/jobs/${jobId}/retry`, { method: "POST" });
  },
  async listReports() {
    await ensureSession();
    return request<MobileReport[]>("/api/v1/mobile/reports");
  },
  async getReport(reportId: string) {
    await ensureSession();
    return request<MobileReport>(`/api/v1/mobile/reports/${reportId}`);
  },
  async saveSubscription(granted: boolean) {
    await ensureSession();
    return request<{ granted: boolean }>("/api/v1/mobile/subscriptions/task-completed", {
      method: "POST",
      data: { granted, version: "v1" }
    });
  },
  async deleteAccount() {
    await ensureSession();
    await request<void>("/api/v1/mobile/me", { method: "DELETE" });
    Taro.removeStorageSync(ACCESS_KEY);
    Taro.removeStorageSync(REFRESH_KEY);
  },
  clearSession() {
    Taro.removeStorageSync(ACCESS_KEY);
    Taro.removeStorageSync(REFRESH_KEY);
  }
};

function readBinary(path: string): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    Taro.getFileSystemManager().readFile({
      filePath: path,
      success: (result) => typeof result.data === "string" ? reject(new Error("无法读取二进制素材")) : resolve(result.data),
      fail: () => reject(new Error("无法读取所选素材"))
    });
  });
}

async function uploadBinary(
  uploadUrl: string,
  data: ArrayBuffer,
  headers: Record<string, string>,
  direct: boolean
): Promise<void> {
  const token = Taro.getStorageSync<string>(ACCESS_KEY);
  const absolute = /^https?:\/\//i.test(uploadUrl);
  const response = await Taro.request({
    url: absolute ? uploadUrl : `${MOCHI_API_BASE}${uploadUrl}`,
    method: "PUT",
    data,
    header: {
      ...(!direct && token ? { authorization: `Bearer ${token}` } : {}),
      ...headers
    }
  });
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw new ApiError(`UPLOAD_${response.statusCode}`, "文件上传失败", true);
  }
}

function contentType(name: string) {
  const suffix = name.split(".").pop()?.toLowerCase();
  return ({ mp4: "video/mp4", mov: "video/quicktime", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", csv: "text/csv", json: "application/json" } as Record<string, string>)[suffix || ""] || "application/octet-stream";
}
