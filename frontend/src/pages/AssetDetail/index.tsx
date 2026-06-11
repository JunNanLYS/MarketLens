import { Button, Card, Col, Empty, Row, Select, Skeleton, Space, Statistic, Table, Tabs, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import dayjs from "dayjs";
import { apiClient, extractErrorMessage } from "@/api/client";
import type { AssetDetail, PageResult, TrackedAsset } from "@/api/types";
import { PnlDisplay } from "@/components/shared/PnlDisplay";
import { formatNumber, formatPercent } from "@/utils/format";

// 标的详情：核心 7 个 tab（行情 / K线 / 财务 / 资金流向 / 分时 / 股东 / AI 报告）
// 其余 5 个（业绩预告 / 分红 / ETF / 行业 / 日历 / 筹码）以"即将开放"占位，避免单页面 1000+ 行不可控
export default function AssetDetailPage() {
  const queryClient = useQueryClient();
  const [assetId, setAssetId] = useState<number | null>(null);

  const assets = useQuery<PageResult<TrackedAsset>>({
    queryKey: ["assets", "all"],
    queryFn: async () => (await apiClient.get<PageResult<TrackedAsset>>("/assets", { params: { page: 1, page_size: 100 } })).data,
    staleTime: 30_000,
  });

  const detail = useQuery<AssetDetail>({
    queryKey: ["asset", assetId],
    queryFn: async () => (await apiClient.get<AssetDetail>(`/assets/${assetId}`)).data,
    enabled: assetId !== null,
    staleTime: 30_000,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["asset", assetId] });
    message.success("已刷新");
  };

  return (
    <Space direction="vertical" size="large" className="w-full">
      <Typography.Title level={3}>标的详情</Typography.Title>

      <Card size="small">
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
          <Button onClick={refresh}>刷新数据</Button>
        </Space>
      </Card>

      {assetId === null ? (
        <Empty description="请选择一个标的" />
      ) : detail.isLoading ? (
        <Skeleton active />
      ) : detail.isError ? (
        <Card><Typography.Text type="danger">加载失败：{extractErrorMessage(detail.error)}</Typography.Text></Card>
      ) : !detail.data ? (
        <Empty />
      ) : (
        <Card title={`${detail.data.symbol} ${detail.data.name ?? ""}`}>
          <Tabs
            items={[
              { key: "quote", label: "行情", children: <QuoteTab detail={detail.data} /> },
              { key: "kline", label: "K线", children: <KlineTab detail={detail.data} /> },
              { key: "finance", label: "财务", children: <FinanceTab detail={detail.data} /> },
              { key: "flow", label: "资金流向", children: <FundFlowTab detail={detail.data} /> },
              { key: "intraday", label: "分时走势", children: <IntradayTab symbol={detail.data.symbol} /> },
              { key: "shareholder", label: "股东结构", children: <ShareholderTab symbol={detail.data.symbol} /> },
              { key: "ai", label: "AI 报告", children: <AiReportTab detail={detail.data} /> },
              { key: "etc", label: "更多", children: <MoreTab /> },
            ]}
          />
        </Card>
      )}
    </Space>
  );
}

function QuoteTab({ detail }: { detail: AssetDetail }) {
  const q = detail.quote ?? {};
  return (
    <Row gutter={[16, 16]}>
      <Col span={6}><Statistic title="最新价" value={q.price} precision={2} /></Col>
      <Col span={6}><Statistic title="涨跌" value={q.change} precision={2} /></Col>
      <Col span={6}><Statistic title="涨跌幅" valueRender={() => <PnlDisplay value={q.change_pct} />} /></Col>
      <Col span={6}><Statistic title="成交量" value={q.volume} /></Col>
      <Col span={6}><Statistic title="开盘" value={q.open} precision={2} /></Col>
      <Col span={6}><Statistic title="最高" value={q.high} precision={2} /></Col>
      <Col span={6}><Statistic title="最低" value={q.low} precision={2} /></Col>
      <Col span={6}><Statistic title="昨收" value={q.prev_close} precision={2} /></Col>
      <Col span={6}><Statistic title="成交额" value={q.amount} /></Col>
    </Row>
  );
}

function KlineTab({ detail }: { detail: AssetDetail }) {
  const k = detail.kline_summary ?? {};
  return (
    <Row gutter={16}>
      <Col span={6}><Statistic title="MA5" value={k.ma5} precision={2} /></Col>
      <Col span={6}><Statistic title="MA20" value={k.ma20} precision={2} /></Col>
      <Col span={6}><Statistic title="MA60" value={k.ma60} precision={2} /></Col>
      <Col span={6}><Statistic title="趋势" value={k.trend ?? "-"} /></Col>
    </Row>
  );
}

function FinanceTab({ detail }: { detail: AssetDetail }) {
  const f = detail.finance_summary ?? {};
  return (
    <Row gutter={16}>
      <Col span={6}><Statistic title="报告期" value={f.report_period ?? "-"} /></Col>
      <Col span={6}><Statistic title="营收同比" valueRender={() => <PnlDisplay value={f.revenue_yoy} />} /></Col>
      <Col span={6}><Statistic title="EPS" value={f.eps} precision={2} /></Col>
      <Col span={6}><Statistic title="ROE" valueRender={() => <PnlDisplay value={f.roe} />} /></Col>
    </Row>
  );
}

function FundFlowTab({ detail }: { detail: AssetDetail }) {
  const f = detail.fund_flow_summary ?? {};
  return (
    <Row gutter={16}>
      <Col span={8}><Statistic title="5 日主力净流入" valueRender={() => <PnlDisplay value={f.net_flow_5d} />} /></Col>
      <Col span={8}><Statistic title="趋势" value={f.trend ?? "-"} /></Col>
    </Row>
  );
}

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
      <Table size="small" rowKey="time" dataSource={items.slice(0, 50)} columns={columns} pagination={false} />
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
        rowKey={(r) => r.name}
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

function AiReportTab({ detail }: { detail: AssetDetail }) {
  const r = detail.latest_report;
  if (!r) return <Empty description="暂无 AI 报告" />;
  return (
    <Space direction="vertical" className="w-full">
      <Space>
        <Tag color="blue">{r.action}</Tag>
        <Tag>{r.risk_level}</Tag>
        <Typography.Text type="secondary">{dayjs(r.generated_at).format("YYYY-MM-DD HH:mm")}</Typography.Text>
      </Space>
      <Typography.Paragraph>{r.summary}</Typography.Paragraph>
      {r.bullish_reasons && r.bullish_reasons.length > 0 && (
        <Card size="small" title="看多理由">
          {r.bullish_reasons.map((s, i) => <div key={i}>▲ {s}</div>)}
        </Card>
      )}
      {r.bearish_reasons && r.bearish_reasons.length > 0 && (
        <Card size="small" title="看空/风险">
          {r.bearish_reasons.map((s, i) => <div key={i}>▼ {s}</div>)}
        </Card>
      )}
    </Space>
  );
}

function MoreTab() {
  return (
    <Empty
      description={
        <Space direction="vertical">
          <Typography.Text>业绩预告 / 分红记录 / ETF / 行业板块 / 日历 / 筹码</Typography.Text>
          <Typography.Text type="secondary" className="text-xs">
            这些 tab 暂以"即将开放"占位，详细实现请见 MIGRATION_PLAN.md Phase 3f
          </Typography.Text>
        </Space>
      }
    />
  );
}
