import { Modal } from "antd";
import { extractErrorMessage, showErrorMessage } from "@/api/client";

interface Props {
  title?: string;
  content?: string;
  okText?: string;
  cancelText?: string;
  onConfirm: () => void | Promise<void>;
}

/**
 * 简化版确认弹窗（DESIGN.md §4.10）：
 * - 危险操作：okButtonProps.danger = true + 红色 token
 * - 禁用 ESC 关闭：keyboard = false（避免误关确认框）
 * - 异步失败时显式提示而不是静默吞掉
 * - 居中布局 + 圆角 12px（继承 global.css 卡片样式）
 */
export function confirmDelete({
  title = "确认删除",
  content = "此操作不可撤销",
  okText = "🗑️  确认删除",
  cancelText = "取消",
  onConfirm,
}: Props) {
  Modal.confirm({
    title,
    content,
    okText,
    cancelText,
    okButtonProps: { danger: true },
    keyboard: false,
    width: 420,
    centered: true,
    onOk: async () => {
      try {
        await onConfirm();
      } catch (error) {
        showErrorMessage(`操作失败：${extractErrorMessage(error)}`);
        throw error;
      }
    },
  });
}
