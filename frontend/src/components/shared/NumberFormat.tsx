import { formatWithUnit } from "@/utils/format";

interface Props {
  value: number | null | undefined;
}

// 数字格式化：自动选择 万/亿 单位
export function NumberFormat({ value }: Props) {
  return <span className="tabular-nums">{formatWithUnit(value)}</span>;
}
