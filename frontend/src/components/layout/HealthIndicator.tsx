import axios from "axios";
import { Badge, Space, Typography } from "antd";
import type { HealthResponse } from "@/api/types";
import { useHealthCheck } from "@/hooks/useHealthCheck";

function resolveHealthPayload(data: HealthResponse | undefined, error: unknown): HealthResponse | null {
  if (data) {
    return data;
  }

  if (axios.isAxiosError(error)) {
    const payload = error.response?.data as Partial<HealthResponse> | undefined;
    if (payload?.status === "degraded") {
      return {
        status: "degraded",
        database: payload.database === "error" ? "error" : "ok",
        scheduler: payload.scheduler === "error" ? "error" : "ok",
      };
    }
  }

  return null;
}

function getDegradedReason(payload: HealthResponse): string {
  const parts = [
    payload.database === "error" ? "数据库" : null,
    payload.scheduler === "error" ? "调度器" : null,
  ].filter((value): value is string => value !== null);

  return parts.length > 0 ? `（${parts.join(" / ")}异常）` : "";
}

// 侧边栏顶部：API 健康指示器（正常/降级/失败三态）。
export function HealthIndicator() {
  const { data, error, isLoading, isError } = useHealthCheck();

  if (isLoading) {
    return (
      <Space>
        <Badge status="processing" />
        <Typography.Text type="secondary">检测中…</Typography.Text>
      </Space>
    );
  }

  const payload = resolveHealthPayload(data, error);
  if (payload?.status === "degraded") {
    return (
      <Space>
        <Badge status="warning" />
        <Typography.Text type="warning">API 已降级{getDegradedReason(payload)}</Typography.Text>
      </Space>
    );
  }

  if (!isError && payload?.status === "ok") {
    return (
      <Space>
        <Badge status="success" />
        <Typography.Text type="success">API 已连接</Typography.Text>
      </Space>
    );
  }

  return (
    <Space>
      <Badge status="error" />
      <Typography.Text type="danger">API 连接失败</Typography.Text>
    </Space>
  );
}
