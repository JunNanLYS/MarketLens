import { Modal } from "antd";

interface Props {
  title?: string;
  content?: string;
  onConfirm: () => void;
}

// 简化版确认弹窗：直接通过 Modal.confirm 触发
export function confirmDelete({ title = "确认删除", content = "此操作不可撤销", onConfirm }: Props) {
  Modal.confirm({
    title,
    content,
    okText: "确认",
    cancelText: "取消",
    okButtonProps: { danger: true },
    onOk: onConfirm,
  });
}
