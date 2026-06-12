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
  sentiment?: "positive" | "negative" | "neutral" | null;
  importance?: number | null;
  related_symbols?: string[] | null;
  collected_at?: string;
  // 2026-06-12 升级：DeepSeek 情感分析完整结果透出
  ai_scored?: boolean;            // true = 走过 DeepSeek；false = 迁移前数据或本次分析失败
  confidence?: number | null;     // 0~1 原始置信度（to_db_value 阈值降级前的真值）
  sentiment_reason?: string | null; // 一句话审计理由
  sectors?: string[] | null;      // 受影响板块（暂未在 NewsList 渲染，留作 UI 后续接入）
}

export interface HealthResponse {
  status: "ok" | "degraded";
  database: "ok" | "error";
  scheduler: "ok" | "error";
}

export interface AIReport {
  id: number;
  symbol: string;
  name?: string | null;
  action: "buy" | "sell" | "watch" | "avoid";
  confidence: number;
  risk_level: "low" | "medium" | "high";
  summary?: string | null;
  bullish_reasons?: string[] | null;
  bearish_reasons?: string[] | null;
  key_risks?: string[] | null;
  data_used?: Array<{ source: string; data_type?: string; collected_at?: string }>;
  generated_at: string;
}

export interface GenerateReportsResponse {
  status: string;
  generated: number;
  skipped: number;
}

export interface Account {
  id: number;
  name: string;
  broker?: string | null;
  currency: string;
  notes?: string | null;
  created_at?: string;
  deleted_at?: string | null;
}

export interface Transaction {
  id: number;
  account_id: number;
  symbol: string;
  type: "buy" | "sell" | "dividend" | "split";
  quantity: number;
  price: number;
  fee?: number;
  currency?: string | null;
  trade_date: string;
  notes?: string | null;
  created_at?: string;
}

export interface Position {
  account_id: number;
  symbol: string;
  name?: string | null;
  total_qty: number;
  avg_cost: number;
  current_price?: number | null;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  unrealized_pnl_pct?: number | null;
}

export interface RealizedPnlItem {
  account_id: number;
  symbol: string;
  total_sell_qty: number;
  realized_pnl: number;
}

export interface AssetDetail extends TrackedAsset {
  quote?: {
    price?: number;
    change?: number;
    change_pct?: number;
    open?: number;
    high?: number;
    low?: number;
    prev_close?: number;
    volume?: number;
    amount?: number;
    collected_at?: string;
  } | null;
  kline_summary?: { ma5?: number; ma20?: number; ma60?: number; trend?: string } | null;
  finance_summary?: {
    report_period?: string;
    revenue_yoy?: number;
    eps?: number;
    roe?: number;
  } | null;
  fund_flow_summary?: { net_flow_5d?: number; trend?: string } | null;
  latest_report?: AIReport | null;
}



