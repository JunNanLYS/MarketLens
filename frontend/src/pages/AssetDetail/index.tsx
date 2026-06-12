import { Button, Card, Empty, Select, Skeleton, Space, Statistic, Table, Tabs, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect, useCallback } from "react";
import dayjs from "dayjs";
import { Panel, Group, Separator } from "react-resizable-panels";
import type { Layout } from "react-resizable-panels";
import { apiClient, extractErrorMessage } from "@/api/client";
import type { AssetDetail as AssetDetailType, PageResult, TrackedAsset } from "@/api/types";
import { PageHeader } from "@/components/shared/PageHeader";
import { PnlDisplay } from "@/components/shared/PnlDisplay";
import { CollectionTimeline } from "@/components/shared/CollectionTimeline";
import { QueryErrorState } from "@/components/shared/QueryErrorState";
import { StatusTag } from "@/components/shared/StatusTag";
import { formatNumber, formatPercent } from "@/utils/format";

// 布局持久化 key
const LAYOUT_KEY = "marketlens:layout:asset-resizer";

const PANEL_IDS = { left: "fundamental", middle: "chart", right: "ai" } as const;

function loadLayout(): Layout | null {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return null;
}

function saveLayout(layout: Layout) {
  try {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout));
  } catch { /* ignore */ }
}

// 判断窄屏
function useIsNarrow() {
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && window.innerWidth < 1024);
  useEffect(() => {
    const mql = window.matchMedia("(max-width: 1023px)");
    const handler = (e: MediaQueryListEvent) => setNarrow(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);
  return narrow;
}

// 标的详情：三栏可拖拽布局（桌面）或 Tabs（窄屏）
export default function AssetDetailPage() {
  const queryClient = useQueryClient();
  const [assetId, setAssetId] = useState<number | null>(null);

  const assets = useQuery<PageResult<TrackedAsset>>({
    queryKey: ["assets", "all"],
    queryFn: async () => (await apiClient.get<PageResult<TrackedAsset>>("/assets", { params: { page: 1, page_size: 100 } })).data,
    staleTime: 30_000,
  });

  const detail = useQuery<AssetDetailType>({
    queryKey: ["asset", assetId],
    queryFn: async () => (await apiClient.get<AssetDetailType>(`/assets/${assetId}`)).data,
    enabled: assetId !== null,
    staleTime: 30_000,
  });

  const refresh = async () => {
    try {
      await queryClient.invalidateQueries({ queryKey: ["asset", assetId] });
      message.success("已刷新");
    } catch {
      message.error("刷新失败");
    }
  };

  const narrow = useIsNarrow();

  const content = assetId === null ? (
    <Empty description="请选择一个标的" />
  ) : detail.isLoading ? (
    <Skeleton active />
  ) : detail.isError ? (
    <QueryErrorState error={detail.error} onRetry={detail.refetch} />
  ) : !detail.data ? (
    <Empty />
  ) : narrow ? (
    <NarrowLayout detail={detail.data} onRefresh={refresh} refreshing={detail.isFetching} />
  ) : (
    <WideLayout detail={detail.data} onRefresh={refresh} refreshing={detail.isFetching} />
  );

  return (
    <Space direction="vertical" size={24} className="w-full">
      <PageHeader
        title="标的详情"
        subtitle="基本面 / 行情 / AI 报告 三栏联动"
      />
      <Card size="small" className="w-full">
        <Space wrap>
          <Select
            showSearch
            placeholder="选择标的"
            style={{ width: 280 }}
            value={assetId ?? undefined}
            onChange={setAssetId}
            optionFilterProp="label"
            loading={assets.isLoading}
            options={(assets.data?.items ?? []).map((a) => ({ value: a.id, label: `${a.symbol} ${a.name ?? ""}` }))}
          />
          <Button onClick={refresh} loading={detail.isFetching}>刷新数据</Button>
        </Space>
      </Card>
      {content}
    </Space>
  );
}

// ─── 三栏可拖拽布局（≥1024px）────────────────────────────
function WideLayout({ detail, onRefresh, refreshing }: { detail: AssetDetailType; onRefresh: () => void; refreshing: boolean }) {
  const defaultLayout: Layout = loadLayout() ?? { [PANEL_IDS.left]: 25, [PANEL_IDS.middle]: 50, [PANEL_IDS.right]: 25 };

  const handleLayoutChange = useCallback((layout: Layout) => {
    saveLayout(layout);
  }, []);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <Group orientation="horizontal" onLayoutChanged={handleLayoutChange} defaultLayout={defaultLayout} className="flex-1 min-h-0">
        <Panel id={PANEL_IDS.left} minSize={15} className="overflow-auto">
          <div className="pr-2 h-full">
            <FundamentalPanel detail={detail} />
          </div>
        </Panel>
        <Separator className="w-3 flex items-center justify-center cursor-col-resize hover:bg-[var(--color-primary)]/20 transition-colors group" aria-label="拖拽以调整宽度">
          <div className="h-full w-0.5 bg-[var(--color-border-strong)] group-hover:bg-[var(--color-primary)] transition-colors" />
        </Separator>

        <Panel id={PANEL_IDS.middle} minSize={30} className="overflow-auto">
          <div className="px-2 h-full">
            <ChartPanel detail={detail} />
          </div>
        </Panel>
        <Separator className="w-3 flex items-center justify-center cursor-col-resize hover:bg-[var(--color-primary)]/20 transition-colors group" aria-label="拖拽以调整宽度">
          <div className="h-full w-0.5 bg-[var(--color-border-strong)] group-hover:bg-[var(--color-primary)] transition-colors" />
        </Separator>

        <Panel id={PANEL_IDS.right} minSize={15} className="overflow-auto">
          <div className="pl-2 h-full">
            <AiPanel detail={detail} onRefresh={onRefresh} refreshing={refreshing} />
          </div>
        </Panel>
      </Group>
    </div>
  );
}

// ─── 窄屏 Tabs 布局（<1024px）────────────────────────────
function NarrowLayout({ detail, onRefresh, refreshing }: { detail: AssetDetailType; onRefresh: () => void; refreshing: boolean }) {
  return (
    <Card title={`${detail.symbol} ${detail.name ?? ""}`} className="w-full">
      <Tabs
        items={[
          { key: "fundamental", label: "基本面", children: <FundamentalPanel detail={detail} /> },
          { key: "chart", label: "行情/K线", children: <ChartPanel detail={detail} /> },
          { key: "ai", label: "AI 报告", children: <AiPanel detail={detail} onRefresh={onRefresh} refreshing={refreshing} /> },
          { key: "intraday", label: "分时走势", children: <IntradayTab symbol={detail.symbol} /> },
          { key: "shareholder", label: "股东结构", children: <ShareholderTab symbol={detail.symbol} /> },
          { key: "collection", label: "采集历史", children: <CollectionTimeline symbol={detail.symbol} /> },
        ]}
      />
    </Card>
  );
}

// ─── 面板：基本面（财务 + 资金流向）────────────────────────
function FundamentalPanel({ detail }: { detail: AssetDetailType }) {
  const f = detail.finance_summary ?? {};
  const flow = detail.fund_flow_summary ?? {};
  return (
    <Space direction="vertical" className="w-full" size="middle">
      <Card size="small" title="财务摘要" className="w-full">
        <Space direction="vertical" className="w-full">
          <Statistic title="报告期" value={f.report_period ?? "-"} />
          <Statistic title="营收同比" valueRender={() => <PnlDisplay value={f.revenue_yoy} mode="text" />} />
          <Statistic title="EPS" value={f.eps} precision={2} />
          <Statistic title="ROE" valueRender={() => <PnlDisplay value={f.roe} mode="text" />} />
        </Space>
      </Card>
      <Card size="small" title="资金流向" className="w-full">
        <Space direction="vertical" className="w-full">
          <Statistic title="5 日主力净流入" valueRender={() => <PnlDisplay value={flow.net_flow_5d} mode="text" />} />
          <Statistic title="趋势" value={flow.trend ?? "-"} />
        </Space>
      </Card>
    </Space>
  );
}

// ─── 面板：行情 + K 线 ───────────────────────────────
function ChartPanel({ detail }: { detail: AssetDetailType }) {
  const q = detail.quote ?? {};
  const k = detail.kline_summary ?? {};
  return (
    <Space direction="vertical" className="w-full" size="middle">
      <Card size="small" title="行情" className="w-full">
        <div className="grid grid-cols-3 gap-3">
          <Statistic title="最新价" value={q.price} precision={2} />
          <Statistic title="涨跌" value={q.change} precision={2} />
          <Statistic title="涨跌幅" valueRender={() => <PnlDisplay value={q.change_pct} mode="text" />} />
          <Statistic title="开盘" value={q.open} precision={2} />
          <Statistic title="最高" value={q.high} precision={2} />
          <Statistic title="最低" value={q.low} precision={2} />
          <Statistic title="昨收" value={q.prev_close} precision={2} />
          <Statistic title="成交量" value={q.volume} />
          <Statistic title="成交额" value={q.amount} />
        </div>
      </Card>
      <Card size="small" title="K 线指标" className="w-full">
        <div className="grid grid-cols-2 gap-3">
          <Statistic title="MA5" value={k.ma5} precision={2} />
          <Statistic title="MA20" value={k.ma20} precision={2} />
          <Statistic title="MA60" value={k.ma60} precision={2} />
          <Statistic title="趋势" value={k.trend ?? "-"} />
        </div>
      </Card>
    </Space>
  );
}

// ─── 面板：AI 报告 ──────────────────────────────────
function AiPanel({ detail, onRefresh, refreshing }: { detail: AssetDetailType; onRefresh: () => void; refreshing: boolean }) {
  const r = detail.latest_report;
  if (!r) {
    return (
      <Space direction="vertical" className="w-full">
        <Card size="small" title="AI 报告" className="w-full">
          <Empty description="暂无 AI 报告">
            <Button onClick={onRefresh} loading={refreshing}>刷新数据</Button>
          </Empty>
        </Card>
        <CollectionTimeline symbol={detail.symbol} />
      </Space>
    );
  }
  return (
    <Space direction="vertical" className="w-full">
      <Card size="small" title="AI 报告" extra={<Button size="small" onClick={onRefresh} loading={refreshing}>刷新</Button>} className="w-full">
        <Space direction="vertical" className="w-full" size={10}>
          <Space size={6}>
            <StatusTag value={r.action} variantMap={{ [r.action]: r.action === "buy" ? "success" : r.action === "sell" ? "error" : "info" }} labelMap={{ [r.action]: r.action }} />
            <StatusTag value={r.risk_level} variantMap={{ [r.risk_level]: r.risk_level === "high" ? "error" : r.risk_level === "medium" ? "warning" : "success" }} labelMap={{ [r.risk_level]: r.risk_level }} />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>{dayjs(r.generated_at).format("YYYY-MM-DD HH:mm")}</Typography.Text>
          </Space>
          <Typography.Paragraph style={{ marginBottom: 0 }}>{r.summary}</Typography.Paragraph>
          {r.bullish_reasons && r.bullish_reasons.length > 0 && (
            <Card size="small" type="inner" title="看多理由" style={{ background: "var(--color-success-soft)" }}>
              {r.bullish_reasons.map((s, i) => <div key={i} style={{ color: "var(--color-success)" }}>▲ {s}</div>)}
            </Card>
          )}
          {r.bearish_reasons && r.bearish_reasons.length > 0 && (
            <Card size="small" type="inner" title="看空/风险" style={{ background: "var(--color-error-soft)" }}>
              {r.bearish_reasons.map((s, i) => <div key={i} style={{ color: "var(--color-error)" }}>▼ {s}</div>)}
            </Card>
          )}
        </Space>
      </Card>
      <CollectionTimeline symbol={detail.symbol} />
    </Space>
  );
}

// ─── 原 Tabs 子组件保留供窄屏 fallback ──────────────────

function isNoDataError(error: unknown): boolean {
  return (error as { response?: { status?: number } } | undefined)?.response?.status === 404;
}

function QueryEmptyState({
  description,
  actionLabel,
  onRefresh,
  loading,
}: {
  description: string;
  actionLabel: string;
  onRefresh: () => void;
  loading: boolean;
}) {
  return (
    <Space direction="vertical" className="w-full" align="center">
      <Empty
        description={
          <Space direction="vertical" size="small">
            <Typography.Text>{description}</Typography.Text>
            <Typography.Text type="secondary">可手动拉取一次并写入本地数据库。</Typography.Text>
          </Space>
        }
      />
      <Button onClick={onRefresh} loading={loading}>{actionLabel}</Button>
    </Space>
  );
}

function IntradayTab({ symbol }: { symbol: string }) {
  const queryClient = useQueryClient();
  const queryKey = ["minute", symbol] as const;
  const m = useMutation({
    mutationFn: async () => (await apiClient.post(`/data/minute/${symbol}/refresh`)).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey });
      message.success("分时数据已更新");
    },
    onError: (err) => message.error(`拉取失败：${extractErrorMessage(err)}`),
  });
  const data = useQuery<{ items: Array<{ time: string; price: number; volume: number; avg_price?: number }>; total: number; symbol: string }>({
    queryKey,
    queryFn: async () => (await apiClient.get(`/data/minute/${symbol}`)).data,
    staleTime: 300_000,
    retry: (failureCount, error) => !isNoDataError(error) && failureCount < 3,
  });

  const columns: ColumnsType<{ time: string; price: number; volume: number; avg_price?: number }> = [
    { title: "时间", dataIndex: "time" },
    { title: "价格", dataIndex: "price", render: (v: number) => formatNumber(v) },
    { title: "成交量", dataIndex: "volume" },
    { title: "均价", dataIndex: "avg_price", render: (v?: number) => formatNumber(v) },
  ];

  if (data.isLoading) {
    return <Skeleton active />;
  }

  if (data.isError && isNoDataError(data.error)) {
    return (
      <QueryEmptyState
        description="暂无已落库的分时数据"
        actionLabel="立即拉取分时"
        onRefresh={() => m.mutate()}
        loading={m.isPending}
      />
    );
  }

  if (data.isError) {
    return <Card size="small"><Typography.Text type="danger">加载失败：{extractErrorMessage(data.error)}</Typography.Text></Card>;
  }

  const items = data.data?.items ?? [];
  if (items.length === 0) {
    return (
      <QueryEmptyState
        description="暂无已落库的分时数据"
        actionLabel="立即拉取分时"
        onRefresh={() => m.mutate()}
        loading={m.isPending}
      />
    );
  }

  return (
    <Space direction="vertical" className="w-full">
      <Button onClick={() => m.mutate()} loading={m.isPending}>手动刷新</Button>
      <Table size="small" rowKey={(_, i) => `minute-${i}`} dataSource={items.slice(0, 50)} columns={columns} pagination={false} />
    </Space>
  );
}

function ShareholderTab({ symbol }: { symbol: string }) {
  const queryClient = useQueryClient();
  const queryKey = ["shareholder", symbol] as const;
  const m = useMutation({
    mutationFn: async () => (await apiClient.post(`/data/shareholder/${symbol}/refresh`)).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey });
      message.success("股东数据已更新");
    },
    onError: (err) => message.error(`拉取失败：${extractErrorMessage(err)}`),
  });
  const data = useQuery<{ top_shareholders?: Array<{ name: string; shares: number; ratio: number }>; holder_count_history?: Array<{ date: string; total_holders: number }>; symbol: string }>({
    queryKey,
    queryFn: async () => (await apiClient.get(`/data/shareholder/${symbol}`)).data,
    staleTime: 300_000,
    retry: (failureCount, error) => !isNoDataError(error) && failureCount < 3,
  });

  if (data.isLoading) {
    return <Skeleton active />;
  }

  if (data.isError && isNoDataError(data.error)) {
    return (
      <QueryEmptyState
        description="暂无已落库的股东结构数据"
        actionLabel="立即拉取股东数据"
        onRefresh={() => m.mutate()}
        loading={m.isPending}
      />
    );
  }

  if (data.isError) {
    return <Card size="small"><Typography.Text type="danger">加载失败：{extractErrorMessage(data.error)}</Typography.Text></Card>;
  }

  const topShareholders = data.data?.top_shareholders ?? [];
  const holderCountHistory = data.data?.holder_count_history ?? [];
  if (topShareholders.length === 0 && holderCountHistory.length === 0) {
    return (
      <QueryEmptyState
        description="暂无已落库的股东结构数据"
        actionLabel="立即拉取股东数据"
        onRefresh={() => m.mutate()}
        loading={m.isPending}
      />
    );
  }

  return (
    <Space direction="vertical" className="w-full">
      <Button onClick={() => m.mutate()} loading={m.isPending}>手动刷新</Button>
      <Table
        size="small"
        rowKey={(_, i) => `shareholder-${i}`}
        title={() => "前 10 大股东"}
        dataSource={topShareholders}
        pagination={false}
        columns={[
          { title: "股东", dataIndex: "name" },
          { title: "持股数", dataIndex: "shares" },
          { title: "持股比例", dataIndex: "ratio", render: (v: number) => formatPercent(v) },
        ]}
      />
      <Table
        size="small"
        rowKey="date"
        title={() => "股东户数历史"}
        dataSource={holderCountHistory}
        pagination={false}
        columns={[
          { title: "日期", dataIndex: "date" },
          { title: "户数", dataIndex: "total_holders" },
        ]}
      />
    </Space>
  );
}