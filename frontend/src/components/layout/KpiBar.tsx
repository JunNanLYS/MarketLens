import { Space, Statistic, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { Position, RealizedPnlItem, HealthResponse } from "@/api/types";
import { NumberFormat } from "@/components/shared/NumberFormat";
import { PnlDisplay } from "@/components/shared/PnlDisplay";

interface KpiData {
  totalValue: number;
  realizedPnl: number;
  unrealizedPnl: number;
  healthOk: boolean | null; // null = loading
}

function useKpiData(): KpiData {
  const positions = useQuery<Position[]>({
    queryKey: ["positions"],
    queryFn: async () => (await apiClient.get<Position[]>("/positions")).data,
    staleTime: 30_000,
  });

  const realized = useQuery<{ items: RealizedPnlItem[] }>({
    queryKey: ["positions", "realized-pnl"],
    queryFn: async () => (await apiClient.get("/positions/realized-pnl")).data,
    staleTime: 30_000,
  });

  const health = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: async () => (await apiClient.get<HealthResponse>("/health")).data,
    staleTime: 30_000,
  });

  const posData = positions.data ?? [];
  const totalValue = posData.reduce((s, p) => s + (p.market_value ?? 0), 0);
  const unrealizedPnl = posData.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0);
  const realizedPnl = (realized.data?.items ?? []).reduce((s, p) => s + p.realized_pnl, 0);
  const healthOk = health.data ? health.data.status === "ok" : null;

  return { totalValue, realizedPnl, unrealizedPnl, healthOk };
}

// 顶部全局 KPI 条：总市值 / 已实现盈亏 / 浮动盈亏 / 数据源健康
export function KpiBar() {
  const { totalValue, realizedPnl, unrealizedPnl, healthOk } = useKpiData();

  return (
    <Space
      size="large"
      style={{ overflowX: "auto", whiteSpace: "nowrap" }}
      className="kpi-bar"
    >
      <Statistic
        title={<Typography.Text type="secondary" style={{ fontSize: 12 }}>总市值</Typography.Text>}
        value={totalValue}
        precision={2}
        formatter={(v) => <NumberFormat value={v as number} />}
      />
      <Statistic
        title={<Typography.Text type="secondary" style={{ fontSize: 12 }}>已实现盈亏</Typography.Text>}
        value={realizedPnl}
        precision={2}
        valueStyle={realizedPnl >= 0 ? { color: "var(--color-success)" } : { color: "var(--color-error)" }}
        formatter={() => <PnlDisplay value={realizedPnl} mode="text" />}
      />
      <Statistic
        title={<Typography.Text type="secondary" style={{ fontSize: 12 }}>浮动盈亏</Typography.Text>}
        value={unrealizedPnl}
        precision={2}
        valueStyle={unrealizedPnl >= 0 ? { color: "var(--color-success)" } : { color: "var(--color-error)" }}
        formatter={() => <PnlDisplay value={unrealizedPnl} mode="text" />}
      />
      <Statistic
        title={<Typography.Text type="secondary" style={{ fontSize: 12 }}>数据源</Typography.Text>}
        value={healthOk === null ? "…" : healthOk ? "正常" : "异常"}
        valueStyle={healthOk === null ? {} : healthOk ? { color: "var(--color-success)" } : { color: "var(--color-error)" }}
      />
    </Space>
  );
}