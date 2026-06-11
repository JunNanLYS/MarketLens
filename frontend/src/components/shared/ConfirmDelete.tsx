import { Modal } from "antd";
import { extractErrorMessage, showErrorMessage } from "@/api/client";

interface Props {
  title?: string;
  content?: string;
  onConfirm: () => void | Promise<void>;
}

// 简化版确认弹窗：保留 Promise 链，异步失败时显式提示而不是静默吞掉。
export function confirmDelete({ title = "确认删除", content = "此操作不可撤销", onConfirm }: Props) {
  Modal.confirm({
    title,
    content,
    okText: "确认",
    cancelText: "取消",
    okButtonProps: { danger: true },
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
