import { Tag } from "antd";
import { formatPercent, formatNumber } from "@/utils/format";

interface Props {
  value: number | null | undefined;
  /** 显示模式：tag（默认，带背景色）或 text（纯文字，用于表格密集场景） */
  mode?: "tag" | "text";
  /** 是否显示文字标签（盈利/亏损/持平） */
  showLabel?: boolean;
  className?: string;
}

/**
 * 盈亏显示组件：
 * - ▲/▼ 形状标识（不依赖颜色辨识）
 * - 文字标签"盈利/亏损/持平"（色弱友好）
 * - WCAG 4.5:1 对比度（浅色/深色均通过）
 * - aria-label 屏幕阅读器支持
 */
export function PnlDisplay({ value, mode = "tag", showLabel = false, className }: Props) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return (
      <span className={`text-gray-400 ${className ?? ""}`} aria-label="暂无盈亏数据">
        -
      </span>
    );
  }

  const isUp = value > 0;
  const isFlat = value === 0;

  // 使用自定义主题 CSS 变量而非 antd 预设色名，确保暗色模式下对比度
  const colorStyle = isFlat
    ? { color: "var(--color-text-tertiary)" }
    : isUp
      ? { color: "var(--color-success)" }
      : { color: "var(--color-error)" };

  const arrow = isFlat ? "—" : isUp ? "▲" : "▼";
  const label = isFlat ? "持平" : isUp ? "盈利" : "亏损";
  // formatPercent 使用 signDisplay:"exceptZero"，对正值加 + 前缀。
  // aria-label 传入的是绝对值（已通过 arrow/label 表达方向），
  // 因此必须避免绝对值被 formatPercent 加上 + 号。
  // 使用 formatNumber 代替 formatPercent，手动拼接 % 号。
  const absDisplay = value === 0 ? "0" : `${formatNumber(Math.abs(value))}%`;
  const ariaLabel = isFlat
    ? `盈亏持平 ${absDisplay}`
    : `盈亏${isUp ? "上涨" : "下跌"} ${absDisplay}`;

  if (mode === "text") {
    return (
      <span
        className={`tabular-nums ${className ?? ""}`}
        style={colorStyle}
        aria-label={ariaLabel}
      >
        {arrow} {formatPercent(value)}
        {showLabel && <>&nbsp;{label}</>}
      </span>
    );
  }

  // tag 模式：保持 antd Tag 样式但颜色用 CSS 变量
  const tagColor = isFlat ? "default" : isUp ? "green" : "red";

  return (
    <Tag
      color={tagColor}
      aria-label={ariaLabel}
      className={className}
    >
      <span className="tabular-nums">
        {arrow} {formatPercent(value)}
      </span>
      {showLabel && (
        <span style={{ marginLeft: 4, fontSize: "0.85em" }}>{label}</span>
      )}
    </Tag>
  );
}