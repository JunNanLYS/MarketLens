import { Space, Typography } from "antd";
import type { DataSourceStatusItem } from "@/api/types";
import { StatusTag } from "@/components/shared/StatusTag";

interface NeoDataStatusRowProps {
  item?: DataSourceStatusItem;
}

// NeoData token 健康状态行。
// - has_token=false → 错误（无 token）
// - has_token=true, token_verified=true → 成功（token 有效）
// - 已配置但未验证 → 警告（token 过期/未验证）
export function NeoDataStatusRow({ item }: NeoDataStatusRowProps) {
  if (!item) {
    return (
      <Typography.Text type="secondary">
        <span className="status-icon">·</span> 未配置 NeoData 源
      </Typography.Text>
    );
  }
  const healthy = item.has_token && item.token_verified;
  const variant = !item.has_token ? "error" : item.token_verified ? "success" : "warning";
  const label = !item.has_token ? "无 token" : item.token_verified ? "token 有效" : "token 过期/未验证";
  const expires = item.token_expires_at ? new Date(item.token_expires_at).toLocaleString("zh-CN") : "—";
  return (
    <Space direction="vertical" size={6} className="w-full">
      <Space>
        <StatusTag value={label} variantMap={{ [label]: variant }} labelMap={{ [label]: label }} />
        {item.endpoint && (
          <Typography.Text type="secondary" className="text-xs">endpoint: {item.endpoint}</Typography.Text>
        )}
      </Space>
      <Typography.Text type="secondary" className="text-xs">
        token 来源：{item.token_source ?? "—"} ｜ 过期时间：{expires} ｜ 可选源：{item.optional ? "是" : "否"}
      </Typography.Text>
      {healthy ? null : (
        <Typography.Text style={{ color: "var(--color-warning)" }} className="text-xs">
          ⚠ 请使用 workbuddy 工具刷新 token（项目侧只读，无法直接续期）。
        </Typography.Text>
      )}
    </Space>
  );
}
