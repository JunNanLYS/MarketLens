import { Tag } from "antd";
import { formatPercent } from "@/utils/format";

interface Props {
  value: number | null | undefined;
}

// 盈亏显示：红/绿 + 上下箭头（不只依赖颜色），并补充屏幕阅读器可读标签。
export function PnlDisplay({ value }: Props) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return (
      <span className="text-gray-400" aria-label="暂无盈亏数据">
        -
      </span>
    );
  }

  const isUp = value > 0;
  const isFlat = value === 0;
  const color = isFlat ? "default" : isUp ? "green" : "red";
  const arrow = isFlat ? "—" : isUp ? "▲" : "▼";
  const ariaLabel = isFlat
    ? `盈亏持平 ${formatPercent(0)}`
    : `盈亏${isUp ? "上涨" : "下跌"} ${formatPercent(Math.abs(value))}`;

  return (
    <Tag color={color} aria-label={ariaLabel}>
      <span className="tabular-nums">
        {arrow} {formatPercent(value)}
      </span>
    </Tag>
  );
}
