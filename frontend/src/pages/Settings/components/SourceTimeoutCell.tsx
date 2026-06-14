import { Button, InputNumber, Space } from "antd";
import { useEffect, useState } from "react";

interface SourceTimeoutCellProps {
  value: number;
  group: string;
  name: string;
  isPending: boolean;
  onSave: (v: number) => void;
}

// 数据源超时行内编辑：进入/取消/保存。
// - 初始显示"值 + 修改"按钮
// - 进入编辑后显示 InputNumber + 保存/取消
// - 保存立即 PATCH（无需回车）
// - 编辑中（draft != value）且外部 value 变化时不重置 draft，避免丢失用户已编辑内容
// - InputNumber 清空(null)时允许暂存空，提交时若非法则不触发 onSave
export function SourceTimeoutCell({
  value,
  group: _group,
  name: _name,
  isPending,
  onSave,
}: SourceTimeoutCellProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<number | null>(value);

  // 编辑中（用户已改但未保存）且 value 变化（外部 PATCH 成功）时同步 draft
  // 非编辑态首次挂载时初始化 draft
  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  if (!editing) {
    return (
      <Space>
        <span>{value}</span>
        <Button
          size="small"
          type="link"
          style={{ padding: 0 }}
          onClick={() => { setDraft(value); setEditing(true); }}
        >
          修改
        </Button>
      </Space>
    );
  }

  // draft 为 null（用户清空）时禁用保存，避免 silent fallback
  const canSave = draft !== null && draft !== value;

  return (
    <Space size={4}>
      <InputNumber
        size="small"
        min={1}
        max={120}
        value={draft}
        onChange={(v) => setDraft(typeof v === "number" ? v : null)}
        style={{ width: 80 }}
        addonAfter="s"
      />
      <Button
        type="primary"
        size="small"
        loading={isPending}
        disabled={!canSave}
        onClick={() => { if (draft !== null) { onSave(draft); setEditing(false); } }}
      >
        保存
      </Button>
      <Button size="small" onClick={() => setEditing(false)}>
        取消
      </Button>
    </Space>
  );
}
