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

// /api/v1/data-sources/status 端点返回的扩展字段。
// 不同 provider 类型附加的字段不一致（NeoData 有 token_*、WeStock 有 command*、普通 HTTP 有 endpoint），
// 所以统一用可选字段表达，避免在父类强制收敛。
export interface DataSourceStatusItem extends DataSourceItem {
  configured?: boolean;
  has_token?: boolean;
  token_source?: string | null;
  token_expires_at?: string | null;
  token_verified?: boolean;
  command?: string | null;
  executable?: string | null;
  command_resolved?: boolean;
  endpoint?: string | null;
}

export interface DataSourcesConfig {
  structured: DataSourceItem[];
  news: DataSourceItem[];
}

export interface DataSourcesStatus {
  structured: DataSourceStatusItem[];
  news: DataSourceStatusItem[];
  hint?: string;
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

// 新闻重要性档位（与 backend collectors 中 importance 取值保持一致）
export type NewsImportance = "normal" | "high" | "low";

export const IMPORTANCE_LABELS: Record<string, string> = {
  normal: "普通",
  high: "重要",
  low: "次要",
};

export interface NewsItem {
  id: number;
  title: string;
  source?: string | null;
  url?: string | null;
  content?: string | null;
  summary?: string | null;
  published_at?: string | null;
  sentiment?: "positive" | "negative" | "neutral" | null;
  // 后端 2026-06 起将 importance 改为字符串档位（normal/high/low）
  importance?: NewsImportance | string | null;
  // 后端返回空列表时为 []，从不返回 null；用可选 + 默认 [] 处理
  related_symbols?: string[];
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
  // name 字段：列表端点不返回，仅详情端点（GET /ai-reports/{id} /asset/{symbol} 详情）有
  name?: string | null;
  action: "buy" | "sell" | "watch" | "avoid";
  confidence: number;
  risk_level: "low" | "medium" | "high";
  summary?: string | null;
  bullish_reasons?: string[] | null;
  bearish_reasons?: string[] | null;
  key_risks?: string[] | null;
  data_used?: Array<{ source: string; data_type?: string; collected_at?: string }>;
  // 2026-06-12 升级: sector_exposure / news_ai_scored_pct 从 ai_analyzer.analyze 透出
  sector_exposure?: Array<{
    sector: string;
    count: number;
    positive: number;
    negative: number;
    neutral: number;
    avg_confidence: number | null;
  }> | null;
  // 0~100 浮点; null = 无新闻证据或全部未评分
  news_ai_scored_pct?: number | null;
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
  updated_at?: string;
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
  // 后端 CreateTransactionRequest 接受 currency?: str | None；GET 返回时为 str（默认 CNY）
  currency: string;
  trade_date: string;
  notes?: string | null;
  created_at?: string;
  updated_at?: string;
  deleted_at?: string | null;
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
  // 2026-06-08 起后端在 realized-pnl 列表中额外返回 avg_cost，便于前端展示卖出均价
  avg_cost: number;
  realized_pnl: number;
}

// 防御性类型：后端 /positions/realized-pnl 当前返回扁平 { items, total, page, page_size }
// （不带 page_info 包装），前端在 Phase 1 阶段先容忍两种格式：
// - 扁平格式（实际后端契约）：{ items, total?, page?, page_size? }
// - PageResult 格式（未来对齐后）：{ items, page_info }
// RealizedPnlResult 把两种格式的可选字段都列上，UI 层按 `items` 取数即可。
export interface RealizedPnlResult {
  items: RealizedPnlItem[];
  total?: number;
  page?: number;
  page_size?: number;
  page_info?: PageInfo;
}

export interface AssetDetail extends TrackedAsset {
  // 显式重写父类字段，避免子类型在 React 表格中类型变窄
  latest_price?: number | null;
  latest_change_pct?: number | null;
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
  kline_summary?: {
    ma5?: number;
    ma20?: number;
    ma60?: number;
    trend?: string;
    // 2026-06-08 起 K 线汇总暴露最新收盘价，便于图表缺数据时用兜底
    latest_close?: number;
  } | null;
  finance_summary?: {
    report_period?: string;
    revenue_yoy?: number;
    eps?: number;
    roe?: number;
  } | null;
  fund_flow_summary?: { net_flow_5d?: number; trend?: string } | null;
  latest_report?: AIReport | null;
}

// ─── Request 类型：字段名严格匹配 backend Pydantic 模型 ───
//
// 后端约定：
// - POST 创建用 *Request（带 default 值的字段也必须显式传入）
// - PATCH 更新用 *Update（所有字段 Optional，仅传需要改的）
//
// 调用方应在 mutationFn 里把表单值用 omit / pick 收敛到对应请求类型。

export interface CreateAccountRequest {
  name: string;          // min_length=1
  broker?: string | null;
  currency?: string;     // default "CNY"
  notes?: string | null;
}

export interface UpdateAccountRequest {
  name?: string;         // min_length=1，可选
  broker?: string | null;
  currency?: string | null;
  notes?: string | null;
}

export type TransactionType = "buy" | "sell" | "dividend" | "split";

export interface CreateTransactionRequest {
  account_id: number;
  symbol: string;        // min_length=1
  type: TransactionType;
  quantity: number;      // gt 0
  price: number;         // gt 0
  fee?: number;          // default 0
  currency?: string | null;
  trade_date: string;    // ISO 8601 YYYY-MM-DD
  notes?: string | null;
}

export interface UpdateTransactionRequest {
  quantity?: number;     // gt 0
  price?: number;        // gt 0
  fee?: number;
  currency?: string | null;
  trade_date?: string;
  notes?: string | null;
}

export interface CreateAssetRequest {
  symbol: string;
  name?: string | null;
  market?: string | null;
  asset_type?: string;   // default "stock"
  tags?: string[] | null;
  notes?: string | null;
}

// /api/v1/assets/search 端点返回的候选标的。
// 字段对齐 backend.api.assets.search_assets → AssetService.search_assets。
// 缺失字段统一用 `string | null` 表达（外部 Provider 返回不一定齐全）。
export interface AssetSearchResult {
  symbol: string;
  name?: string | null;
  market?: string | null;
  asset_type?: string | null;
  source?: string;          // neodata / sina / westock / local
  already_tracked?: boolean; // true = 已在本地追踪表，避免重复添加
}

export interface UpdateAssetRequest {
  enabled?: boolean;
  tags?: string[] | null;
  notes?: string | null;
}

// /api/v1/settings 返回的可编辑配置
// 字段对齐 backend.api.settings._list_editable
export interface EditableSource {
  group: "structured" | "news";
  name: string;
  provider: string;
  enabled: boolean;
  optional: boolean;
  timeout: number;
}

export interface EditableTask {
  interval: number | null;
  cron: string | null;
}

export interface EditableSettings {
  sources: EditableSource[];
  scheduler: { tasks: Record<string, EditableTask> };
}

export interface SettingsResponse {
  editable: EditableSettings;
}
