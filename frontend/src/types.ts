export type RunStatus = "pending" | "running" | "success" | "failed" | "unknown";

export type ChatRun = {
  run_id: string;
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
  markdown?: string;
};

export type UploadAsset = {
  asset_id: string;
  filename: string;
  content_type: string;
  file_type: "video" | "image" | "csv" | "json" | "other";
  path: string;
  created_at: string;
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
};
