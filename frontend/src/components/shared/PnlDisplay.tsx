import type { CSSProperties } from "react";
import { formatNumber, formatPercent } from "@/utils/format";

interface Props {
  value: number | null | undefined;
  /** 显示模式：tag（默认，带背景色 chip）或 text（纯文字，表格密集场景） */
  mode?: "tag" | "text";
  /** 是否显示文字标签（盈利/亏损/持平） */
  showLabel?: boolean;
  className?: string;
  style?: CSSProperties;
}

/**
 * 盈亏显示组件（DESIGN.md §4.6）：
 * - ▲/▼ 形状标识（不依赖颜色辨识，色弱友好）
 * - 文字标签"盈利/亏损/持平"（WCAG 颜色之外的多重信号）
 * - 全部走 CSS 变量（`var(--color-success/error/text-tertiary)`），暗色模式自动适配
 * - 涨/跌使用 soft 背景 + 主色文字的 chip 风格，圆角 4px
 * - aria-label 屏幕阅读器支持
 */
export function PnlDisplay({ value, mode = "tag", showLabel = false, className, style }: Props) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return (
      <span className={`pnl-empty tabular-nums ${className ?? ""}`} style={style} aria-label="暂无盈亏数据">
        —
      </span>
    );
  }

  const isUp = value > 0;
  const isFlat = value === 0;

  const baseClass = isFlat ? "pnl-flat" : isUp ? "pnl-up" : "pnl-down";
  const arrow = isFlat ? "—" : isUp ? "▲" : "▼";
  const label = isFlat ? "持平" : isUp ? "盈利" : "亏损";

  // 使用 formatPercent 渲染带符号百分比；绝对值用于 aria-label
  const ariaLabel = isFlat
    ? `盈亏持平 ${formatNumber(value)}`
    : `盈亏${isUp ? "上涨" : "下跌"} ${formatPercent(value)}`;

  if (mode === "text") {
    return (
      <span
        className={`tabular-nums ${baseClass} ${className ?? ""}`}
        style={style}
        aria-label={ariaLabel}
      >
        {arrow} {formatPercent(value)}
        {showLabel && <span style={{ marginLeft: 4, fontSize: "0.85em" }}>{label}</span>}
      </span>
    );
  }

  // tag 模式：自定义 span chip，避开 antd Tag 颜色污染
  return (
    <span
      className={`${baseClass} tabular-nums ${className ?? ""}`}
      style={{ display: "inline-flex", alignItems: "center", gap: 4, ...style }}
      aria-label={ariaLabel}
    >
      <span style={{ fontSize: "0.85em" }}>{arrow}</span>
      <span>{formatPercent(value)}</span>
      {showLabel && (
        <span style={{ fontSize: "0.85em", opacity: 0.85 }}>{label}</span>
      )}
    </span>
  );
}
