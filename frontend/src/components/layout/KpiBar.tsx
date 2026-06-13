import {
  forwardRef,
  memo,
  useImperativeHandle,
  useRef,
  type ReactNode,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { Position, RealizedPnlResult, HealthResponse } from "@/api/types";
import { NumberFormat } from "@/components/shared/NumberFormat";
import { PnlDisplay } from "@/components/shared/PnlDisplay";

interface KpiData {
  totalValue: number;
  realizedPnl: number;
  unrealizedPnl: number;
  healthOk: boolean | null; // null = loading
}

function useKpiData(): {
  data: KpiData;
  refetchAll: () => Promise<unknown[]>;
} {
  const positions = useQuery<Position[]>({
    queryKey: ["positions"],
    queryFn: async () => (await apiClient.get<Position[]>("/positions")).data,
    staleTime: 15_000,
  });

  const realized = useQuery<RealizedPnlResult>({
    queryKey: ["positions", "realized-pnl"],
    queryFn: async () => (await apiClient.get<RealizedPnlResult>("/positions/realized-pnl")).data,
    staleTime: 15_000,
  });

  const health = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: async () => (await apiClient.get<HealthResponse>("/health")).data,
    staleTime: 15_000,
  });

  const posData = positions.data ?? [];
  const totalValue = posData.reduce((s, p) => s + (p.market_value ?? 0), 0);
  const unrealizedPnl = posData.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0);
  const realizedPnl = (realized.data?.items ?? []).reduce((s, p) => s + p.realized_pnl, 0);
  const healthOk = health.data ? health.data.status === "ok" : null;

  return {
    data: { totalValue, realizedPnl, unrealizedPnl, healthOk },
    refetchAll: () => Promise.all([positions.refetch(), realized.refetch(), health.refetch()]),
  };
}

export interface KpiBarHandle {
  refetchKpis: () => Promise<unknown[]>;
}

// 单个 KPI chip（DESIGN.md §4.7）：label + value + 视觉分隔
function KpiChip({
  label,
  value,
  renderValue,
}: {
  label: string;
  value?: number;
  renderValue?: () => ReactNode;
}) {
  return (
    <div className="kpi-chip">
      <span className="kpi-chip-label">{label}</span>
      <span className="kpi-chip-value">
        {renderValue
          ? renderValue()
          : value !== undefined
            ? <NumberFormat value={value} />
            : "—"}
      </span>
    </div>
  );
}

// 顶部全局 KPI 条（DESIGN.md §4.7）：4 个 chip，1px 分隔线
// memo 包装：让 AppLayout 父级 re-render 时（路由切换/主题切换），
// KpiBar 不重新渲染（内部 useQuery 引用变化也不影响 props 比较），
// 节省 4 个 chip + NumberFormat + PnlDisplay 的重绘开销。
export const KpiBar = memo(forwardRef<KpiBarHandle>(function KpiBar(_props, ref) {
  const { data, refetchAll } = useKpiData();
  const { totalValue, realizedPnl, unrealizedPnl, healthOk } = data;
  const refetchRef = useRef(refetchAll);
  refetchRef.current = refetchAll;

  useImperativeHandle(
    ref,
    () => ({
      refetchKpis: () => refetchRef.current(),
    }),
    [],
  );

  return (
    <div
      className="kpi-bar"
      style={{ display: "flex", overflowX: "auto", whiteSpace: "nowrap" }}
    >
      <KpiChip label="总市值" value={totalValue} />
      <KpiChip
        label="已实现盈亏"
        renderValue={() => <PnlDisplay value={realizedPnl} mode="text" />}
      />
      <KpiChip
        label="浮动盈亏"
        renderValue={() => <PnlDisplay value={unrealizedPnl} mode="text" />}
      />
      <KpiChip
        label="数据源"
        renderValue={() => {
          if (healthOk === null) {
            return <span className="pnl-empty">…</span>;
          }
          return healthOk ? (
            <span style={{ color: "var(--color-success)" }}>● 正常</span>
          ) : (
            <span style={{ color: "var(--color-error)" }}>● 异常</span>
          );
        }}
      />
    </div>
  );
}));
