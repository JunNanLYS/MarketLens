import { Tag } from "antd";

interface Props {
  value: string | null | undefined;
  colorMap?: Record<string, string>;
  labelMap?: Record<string, string>;
}

// 通用状态标签：空值显示为“未设置”，与真实字符串 "-" 明确区分。
export function StatusTag({ value, colorMap, labelMap }: Props) {
  if (value === null || value === undefined || value === "") {
    return (
      <span className="text-gray-400" aria-label="未设置">
        未设置
      </span>
    );
  }

  const color = colorMap?.[value] ?? "default";
  const label = labelMap?.[value] ?? value;
  return <Tag color={color}>{label}</Tag>;
}
