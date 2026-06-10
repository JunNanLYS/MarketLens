import { Badge, Space, Typography } from "antd";
import { useHealthCheck } from "@/hooks/useHealthCheck";

// 侧边栏顶部：API 健康指示器（绿/红点 + 文字）
export function HealthIndicator() {
  const { data, isLoading, isError } = useHealthCheck();

  if (isLoading) {
    return (
      <Space>
        <Badge status="processing" />
        <Typography.Text type="secondary">检测中…</Typography.Text>
      </Space>
    );
  }

  const ok = !isError && data?.status === "ok";
  return (
    <Space>
      <Badge status={ok ? "success" : "error"} />
      <Typography.Text type={ok ? "success" : "danger"}>
        {ok ? "API 已连接" : "API 连接失败"}
      </Typography.Text>
    </Space>
  );
}
