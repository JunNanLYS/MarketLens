import { Tag } from "antd";

interface Props {
  value: string | null | undefined;
  colorMap?: Record<string, string>;
  labelMap?: Record<string, string>;
}

// 通用状态标签：可注入 color / label 映射
export function StatusTag({ value, colorMap, labelMap }: Props) {
  if (!value) return <span className="text-gray-400">-</span>;
  const color = colorMap?.[value] ?? "default";
  const label = labelMap?.[value] ?? value;
  return <Tag color={color}>{label}</Tag>;
}
