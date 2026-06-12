type StatusVariant = "success" | "error" | "warning" | "info" | "neutral" | "accent";

interface Props {
  value: string | null | undefined;
  /**
   * 状态值到 variant 的映射。
   * 例：{ success: "success", failure: "error", running: "info" }
   * 映射不到的 value 自动用 neutral variant。
   */
  variantMap?: Record<string, StatusVariant>;
  /**
   * 状态值到展示文字的映射。
   * 映射不到则用原 value。
   */
  labelMap?: Record<string, string>;
  /**
   * 状态值到 icon 字符的映射（emoji 或符号）。
   * 例：{ success: "✓", failure: "✕", running: "↻" }
   */
  iconMap?: Record<string, string>;
}

// 每个 variant 配 icon（兜底），WCAG 颜色之外的多重信号
const DEFAULT_ICON: Record<StatusVariant, string> = {
  success: "✓",
  error: "✕",
  warning: "!",
  info: "i",
  neutral: "·",
  accent: "★",
};

/**
 * 通用状态标签（DESIGN.md §4.5）：
 * - 全部走 token（`var(--color-success-soft)` + `var(--color-success)` 等）
 * - 不再透传 antd 颜色名（消除 "green"/"red" 硬编码）
 * - 圆角 4px、字号 12px、padding 2px 8px
 * - 必须配 icon（WCAG 颜色非唯一信号）
 */
export function StatusTag({ value, variantMap, labelMap, iconMap }: Props) {
  if (value === null || value === undefined || value === "") {
    return (
      <span className="status-tag status-tag-neutral" aria-label="未设置">
        <span className="status-icon">·</span>
        <span>未设置</span>
      </span>
    );
  }

  const variant: StatusVariant = variantMap?.[value] ?? "neutral";
  const label = labelMap?.[value] ?? value;
  const icon = iconMap?.[value] ?? DEFAULT_ICON[variant];

  return (
    <span className={`status-tag status-tag-${variant}`} aria-label={label}>
      <span className="status-icon" aria-hidden="true">{icon}</span>
      <span>{label}</span>
    </span>
  );
}
