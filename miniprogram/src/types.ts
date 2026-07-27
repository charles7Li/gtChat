export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export type Session = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: { id: string; status: string };
};

export type MobileJob = {
  id: string;
  query: string;
  route: string;
  status: JobStatus;
  progress: { stage: string; percent: number };
  error_code?: string;
  error_message?: string;
  report_id?: string;
  created_at: string;
};

export type MobileReport = {
  id: string;
  job_id: string;
  title: string;
  summary: string;
  markdown?: string;
  created_at: string;
};

export type UploadAsset = {
  id: string;
  filename: string;
  file_type: "video" | "image" | "csv" | "json";
  status: "pending" | "uploaded" | "rejected";
};

export type ApiErrorPayload = {
  code: string;
  message: string;
  retryable: boolean;
};
