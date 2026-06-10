// 手动补齐的核心响应类型（后端未使用 response_model，codegen 只能拿到 any）
// 实际开发中可以按需扩展；每个接口先用一个宽松的 interface 占位

export interface TrackedAsset {
  id: number;
  symbol: string;
  name?: string | null;
  market?: string | null;
  asset_type?: string;
  enabled?: boolean;
  tags?: string[] | null;
  notes?: string | null;
  created_at?: string;
  updated_at?: string;
  latest_price?: number | null;
  latest_change_pct?: number | null;
  latest_quote_at?: string | null;
}

export interface PageInfo {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface PageResult<T> {
  items: T[];
  page_info: PageInfo;
}

export interface DataSourceItem {
  category: string;
  name: string;
  provider: string;
  type: string;
  enabled: boolean;
  optional: boolean;
  timeout?: number;
}

export interface DataSourcesConfig {
  structured: DataSourceItem[];
  news: DataSourceItem[];
}

export interface TaskStatusItem {
  task_name: string;
  description?: string;
  schedule?: string;
  last_run_at?: string | null;
  last_status?: string | null;
  last_duration_ms?: number | null;
  last_affected_assets?: number | null;
  last_error?: string | null;
  next_run_at?: string | null;
}

export interface TaskLog {
  id: number;
  task_name: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
  error_message?: string | null;
  affected_assets?: number | null;
}

export interface NewsItem {
  id: number;
  title: string;
  source?: string | null;
  url?: string | null;
  content?: string | null;
  summary?: string | null;
  published_at?: string | null;
  sentiment?: "positive" | "negative" | "neutral" | string | null;
  importance?: number | null;
  related_symbols?: string[] | null;
  collected_at?: string;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  database: "ok" | "error";
  scheduler: "ok" | "error";
}
