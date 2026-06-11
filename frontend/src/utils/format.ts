// 数字/货币/百分比格式化
const INVALID_NUMBER_PLACEHOLDER = "-";

interface TaskStatusMeta {
  color?: string;
  label: string;
}

const TASK_STATUS_META_MAP: Record<string, TaskStatusMeta> = {
  success: { color: "green", label: "成功" },
  failure: { color: "red", label: "失败" },
  failed: { color: "red", label: "失败" },
  error: { color: "red", label: "失败" },
  running: { color: "blue", label: "进行中" },
  skipped: { color: "gold", label: "已跳过" },
  pending: { color: undefined, label: "待执行" },
  warning: { color: "orange", label: "警告" },
};

function normalizeFiniteNumber(value: number | null | undefined): number | null {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return null;
  }
  return Object.is(value, -0) ? 0 : value;
}

export function formatNumber(value: number | null | undefined, fractionDigits = 2): string {
  const normalizedValue = normalizeFiniteNumber(value);
  if (normalizedValue === null) return INVALID_NUMBER_PLACEHOLDER;
  return normalizedValue.toLocaleString("zh-CN", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

export function formatPercent(value: number | null | undefined, fractionDigits = 2): string {
  const normalizedValue = normalizeFiniteNumber(value);
  if (normalizedValue === null) return INVALID_NUMBER_PLACEHOLDER;
  return `${normalizedValue.toLocaleString("zh-CN", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
    signDisplay: "exceptZero",
  })}%`;
}

export function formatWithUnit(value: number | null | undefined): string {
  const normalizedValue = normalizeFiniteNumber(value);
  if (normalizedValue === null) return INVALID_NUMBER_PLACEHOLDER;
  const abs = Math.abs(normalizedValue);
  const sign = normalizedValue < 0 ? "-" : "";
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(2)}万`;
  return `${sign}${abs.toFixed(2)}`;
}

export function getTaskStatusMeta(status: string | null | undefined): TaskStatusMeta | null {
  if (!status) return null;
  return TASK_STATUS_META_MAP[status.trim().toLowerCase()] ?? { color: undefined, label: status };
}
