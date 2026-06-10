import { Tag } from "antd";
import { formatPercent } from "@/utils/format";

interface Props {
  value: number | null | undefined;
}

// 盈亏显示：红/绿 + 上下箭头（不只是颜色，避免色盲场景）
export function PnlDisplay({ value }: Props) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className="text-gray-400">-</span>;
  }
  const isUp = value > 0;
  const isFlat = value === 0;
  const color = isFlat ? "default" : isUp ? "green" : "red";
  const arrow = isFlat ? "—" : isUp ? "▲" : "▼";
  return (
    <Tag color={color}>
      <span className="tabular-nums">
        {arrow} {formatPercent(value)}
      </span>
    </Tag>
  );
}
