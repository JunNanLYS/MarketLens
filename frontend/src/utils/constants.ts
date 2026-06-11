// 市场、状态、情绪等中文映射常量
export const MARKET_LABELS: Record<string, string> = {
  sh: "沪市",
  sz: "深市",
  hk: "港股",
  us: "美股",
  fut: "期货",
  hf: "海外期货",
  nf: "国内期货",
};

export const ASSET_TYPE_LABELS: Record<string, string> = {
  stock: "股票",
  etf: "ETF",
  index: "指数",
  future: "期货",
  option: "期权",
  fx: "外汇",
  fund: "基金",
  bond: "债券",
  crypto: "加密货币",
};

export const SENTIMENT_LABELS: Record<string, string> = {
  positive: "看多",
  negative: "看空",
  neutral: "中性",
};

export const SENTIMENT_COLORS: Record<string, string> = {
  positive: "green",
  negative: "red",
  neutral: "default",
};

export const TASK_LABELS: Record<string, string> = {
  quote: "行情采集",
  daily_close: "日收盘采集",
  news: "新闻采集",
  ai_report: "AI 报告生成",
  cleanup: "历史清理",
};
