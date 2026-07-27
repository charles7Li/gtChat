export type RunStatus = "pending" | "queued" | "running" | "cancelling" | "cancelled" | "success" | "failed" | "unknown";

export type ThemeId = "ragdoll" | "siamese" | "calico" | "tabby";

export type ChatRun = {
  run_id: string;
  title?: string;
  query?: string;
  route: string;
  status: RunStatus;
  report_path?: string;
  trace_path?: string;
  manifest_path?: string;
  evidence_path?: string;
  warnings?: Array<Record<string, unknown>>;
  errors?: Array<Record<string, unknown>>;
  created_at: string;
  updated_at?: string;
  markdown?: string;
  stages?: Array<{ name: string; status: string; started_at?: string; ended_at?: string; duration_ms?: number }>;
  error?: string;
  cancel_requested?: boolean;
  allow_live?: boolean;
};

export type UploadAsset = {
  asset_id: string;
  filename: string;
  content_type: string;
  file_type: "video" | "image" | "csv" | "json" | "other";
  path: string;
  created_at: string;
  size: number;
  status: "uploaded" | "processing" | "completed" | "failed";
  result?: Record<string, unknown> | null;
  error?: string | null;
};

export type MonitorJob = {
  job_id?: string;
  name: string;
  enabled: boolean;
  platforms: string[];
  keywords: string[];
  interval_seconds: number;
  allow_live: boolean;
  signals_path?: string;
  output_dir: string;
  rule: {
    min_heat_score?: number;
    min_growth_rate?: number;
    min_rank?: number;
    min_engagement?: number;
    required_sources: string[];
  };
  last_run_at?: string;
  last_result?: Record<string, unknown>;
};
