import {
  AutoComplete,
  Button,
  Card,
  Divider,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Skeleton,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiClient, extractErrorMessage } from "@/api/client";
import type { AssetSearchResult, PageResult, TrackedAsset } from "@/api/types";
import { MARKET_LABELS, ASSET_TYPE_LABELS } from "@/utils/constants";
import { confirmDelete } from "@/components/shared/ConfirmDelete";
import { PageHeader } from "@/components/shared/PageHeader";
import { PnlDisplay } from "@/components/shared/PnlDisplay";
import { QueryErrorState } from "@/components/shared/QueryErrorState";
import { formatNumber } from "@/utils/format";

const ASSET_TYPES = [
  { value: "stock", label: "股票" },
  { value: "etf", label: "ETF" },
  { value: "index", label: "指数" },
  { value: "future", label: "期货" },
  { value: "option", label: "期权" },
  { value: "fx", label: "外汇" },
  { value: "fund", label: "基金" },
  { value: "bond", label: "债券" },
  { value: "crypto", label: "加密货币" },
];

interface AddAssetForm {
  symbol: string;
  name?: string;
  market: string;
  asset_type: string;
  tags?: string;
  notes?: string;
}

// 防抖搜索 hook：
// - keyword 变化后 250ms 才真正发请求；连续输入时只保留最后一次。
// - reqId 序号确保慢请求不会覆盖快请求的结果。
// - 空 keyword 直接清空，不发请求。
function useAssetSearch(keyword: string) {
  const [state, setState] = useState<{
    items: AssetSearchResult[];
    loading: boolean;
    error: string | null;
  }>({ items: [], loading: false, error: null });
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const lastReq = useRef(0);

  useEffect(() => {
    if (timer.current !== undefined) clearTimeout(timer.current);
    const trimmed = keyword.trim();
    if (!trimmed) {
      setState({ items: [], loading: false, error: null });
      return;
    }
    setState((s) => ({ ...s, loading: true, error: null }));
    timer.current = setTimeout(async () => {
      const reqId = ++lastReq.current;
      try {
        const { data } = await apiClient.get<{ items: AssetSearchResult[]; total: number }>(
          "/assets/search",
          { params: { keyword: trimmed, include_local: true } },
        );
        if (reqId !== lastReq.current) return;
        setState({ items: data.items ?? [], loading: false, error: null });
      } catch (err) {
        if (reqId !== lastReq.current) return;
        setState({ items: [], loading: false, error: extractErrorMessage(err) });
      }
    }, 250);
    return () => {
      if (timer.current !== undefined) clearTimeout(timer.current);
    };
  }, [keyword]);

  return state;
}

interface AddModalSearchProps {
  onPick: (asset: AssetSearchResult) => void;
}

// Add Modal 顶部的"搜索标的" AutoComplete。
// 选中候选后调用 onPick 让父组件填表。
function AddModalSearch({ onPick }: AddModalSearchProps) {
  const [keyword, setKeyword] = useState("");
  const search = useAssetSearch(keyword);

  const options = useMemo(
    () =>
      search.items.map((item) => {
        const marketLabel = item.market ? (MARKET_LABELS[item.market] ?? item.market) : "—";
        const typeLabel = item.asset_type ? (ASSET_TYPE_LABELS[item.asset_type] ?? item.asset_type) : "—";
        const tracked = item.already_tracked === true;
        return {
          value: item.symbol,
          label: (
            <div style={{ display: "flex", alignItems: "center", gap: 8, opacity: tracked ? 0.55 : 1 }}>
              <Tag bordered={false} color="blue" style={{ margin: 0 }}>{item.symbol}</Tag>
              <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {item.name || "(无名称)"}
              </span>
              <span style={{ color: "var(--color-text-secondary)", fontSize: 12 }}>{marketLabel} · {typeLabel}</span>
              {tracked && <Tag color="default" style={{ margin: 0 }}>已追踪</Tag>}
            </div>
          ),
          disabled: tracked,
          data: item,
        };
      }),
    [search.items],
  );

  return (
    <div style={{ marginBottom: 8 }}>
      <label
        style={{
          display: "block",
          marginBottom: 6,
          fontSize: 13,
          color: "var(--color-text-secondary)",
        }}
      >
        搜索标的（输入"宁德"等关键词自动联想）
      </label>
      <AutoComplete
        value={keyword}
        options={options}
        onChange={setKeyword}
        onSelect={(_value, option) => {
          const data = (option as { data?: AssetSearchResult }).data;
          if (data) onPick(data);
          setKeyword("");
        }}
        style={{ width: "100%" }}
        placeholder="输入股票 / 基金 / 期货的名称或代码，回车或点击候选填表"
        notFoundContent={
          search.loading ? (
            <Spin size="small" />
          ) : search.error ? (
            <span style={{ color: "var(--color-error)" }}>搜索失败：{search.error}</span>
          ) : keyword.trim() ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <span style={{ color: "var(--color-text-secondary)" }}>
                  未找到 "{keyword.trim()}"
                </span>
              }
            />
          ) : null
        }
      >
        <Input
          size="large"
          allowClear
          prefix={<span aria-hidden>🔍</span>}
          suffix={search.loading ? <Spin size="small" /> : null}
        />
      </AutoComplete>
      <div
        style={{
          fontSize: 12,
          color: "var(--color-text-secondary)",
          marginTop: 6,
          lineHeight: 1.5,
        }}
      >
        支持 A 股 / 港股 / 美股 / 基金 / 期货，由新浪、NeoData、WeStock 等多源聚合。也可跳过搜索，直接在下方手动填写。
      </div>
    </div>
  );
}

// 追踪标的：列表 + 启用/禁用 + 删除 + 添加（含搜索联想）
export default function TrackedAssetsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [market, setMarket] = useState<string | undefined>();
  const [assetType, setAssetType] = useState<string | undefined>();
  const [enabled, setEnabled] = useState<boolean | undefined>();
  const [addOpen, setAddOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [form] = Form.useForm<AddAssetForm>();

  const assets = useQuery<PageResult<TrackedAsset>>({
    queryKey: ["assets", { search, market, asset_type: assetType, enabled }],
    queryFn: async () => {
      const { data } = await apiClient.get<PageResult<TrackedAsset>>("/assets", {
        params: { search, market, asset_type: assetType, enabled, page: 1, page_size: 50 },
      });
      return data;
    },
    staleTime: 30_000,
  });

  const update = useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: Partial<TrackedAsset> }) => {
      await apiClient.patch(`/assets/${id}`, payload);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assets"] }),
    onError: (err) => message.error(`更新失败：${extractErrorMessage(err)}`),
  });

  const remove = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/assets/${id}`);
    },
    onSuccess: () => {
      message.success("已删除");
      queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (err) => message.error(`删除失败：${extractErrorMessage(err)}`),
  });

  const create = useMutation({
    mutationFn: async (values: AddAssetForm) => {
      const tags = values.tags
        ? values.tags.split(",").map((t) => t.trim()).filter(Boolean).slice(0, 10)
        : [];
      await apiClient.post("/assets", {
        symbol: values.symbol,
        name: values.name,
        market: values.market,
        asset_type: values.asset_type,
        tags,
        notes: values.notes,
      });
    },
    onSuccess: () => {
      message.success("已添加");
      setAddOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (err) => message.error(`添加失败：${extractErrorMessage(err)}`),
  });

  // 外部搜索结果行的"一键添加"——不打开 Modal，直接 POST。
  // 成功后 invalidate 两个 query: 顶部资产列表 + 外部搜索结果（让该行变 "已添加"）。
  // 注意：invalidate 不会自动重跑，需要主动 refetch。
  const quickCreate = useMutation({
    mutationFn: async (item: AssetSearchResult) => {
      await apiClient.post("/assets", {
        symbol: item.symbol,
        name: item.name ?? null,
        market: item.market ?? null,
        asset_type: item.asset_type ?? "stock",
      });
    },
    onSuccess: (_data, item) => {
      message.success(`已添加：${item.symbol} ${item.name ?? ""}`);
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      // 重新跑一次外部搜索，让该行的 already_tracked 翻成 true
      externalSearch.refetch();
    },
    onError: (err, item) => {
      // 409 (ASSET_EXISTS) 后端会报，区分出来给更友好的提示
      const detail = extractErrorMessage(err);
      if (detail.includes("已在追踪列表中")) {
        message.warning(`${item.symbol} 已在追踪列表中`);
        externalSearch.refetch();
      } else {
        message.error(`添加失败：${detail}`);
      }
    },
  });

  // 外部搜索：调 /assets/search（多 Provider 聚合），而非 /assets（仅本地表）。
  // 旧实现误用了 /assets，导致"外部搜索"实际只搜本地已追踪列表。
  const externalSearch = useQuery<{ items: AssetSearchResult[]; total: number }>({
    queryKey: ["assets", "external-search", keyword],
    queryFn: async () => {
      const { data } = await apiClient.get<{ items: AssetSearchResult[]; total: number }>(
        "/assets/search",
        { params: { keyword, include_local: true } },
      );
      return data;
    },
    enabled: false,
  });

  const columns: ColumnsType<TrackedAsset> = [
    { title: "代码", dataIndex: "symbol", key: "symbol" },
    { title: "名称", dataIndex: "name", key: "name" },
    {
      title: "市场",
      dataIndex: "market",
      key: "market",
      render: (m?: string) => (m ? <Tag bordered={false}>{MARKET_LABELS[m] ?? m}</Tag> : <span className="pnl-empty">—</span>),
    },
    { title: "类型", dataIndex: "asset_type", key: "asset_type", render: (t?: string) => (t ? ASSET_TYPE_LABELS[t] ?? t : <span className="pnl-empty">—</span>) },
    {
      title: "最新价",
      dataIndex: "latest_price",
      key: "latest_price",
      align: "right",
      className: "tabular-nums",
      render: (v?: number | null) => (v != null ? formatNumber(v) : <span className="pnl-empty">—</span>),
    },
    {
      title: "涨跌幅",
      dataIndex: "latest_change_pct",
      key: "latest_change_pct",
      align: "right",
      render: (v?: number | null) => <PnlDisplay value={v} mode="text" />,
    },
    {
      title: "启用",
      dataIndex: "enabled",
      key: "enabled",
      render: (e: boolean, record) => (
        <Switch
          checked={e}
          onChange={(v) => update.mutate({ id: record.id, payload: { enabled: v } })}
        />
      ),
    },
    {
      title: "操作",
      key: "actions",
      align: "center",
      render: (_, record) => (
        <Button
          danger
          size="small"
          onClick={() =>
            confirmDelete({
              title: "确认删除",
              content: `将删除追踪标的 ${record.symbol}`,
              onConfirm: () => remove.mutateAsync(record.id),
            })
          }
        >
          删除
        </Button>
      ),
    },
  ];

  // 从搜索候选选中后填表。
  // 优先级：搜索结果 > 当前表单值。
  // 若用户已在表单中输入了东西，提示"已覆盖"避免误操作。
  const onPickSearchResult = (item: AssetSearchResult) => {
    form.setFieldsValue({
      symbol: item.symbol,
      name: item.name ?? undefined,
      market: item.market ?? undefined,
      asset_type: item.asset_type ?? "stock",
    });
    message.success(`已填入：${item.symbol} ${item.name ?? ""}`);
  };

  return (
    <Space direction="vertical" size={24} className="w-full">
      <PageHeader
        title="追踪标的"
        subtitle="管理本地追踪的资产清单（数据采集、AI 报告、新闻分析都基于此清单）"
        extra={
          <Space>
            <Button onClick={() => setSearchOpen((v) => !v)}>🔍 外部搜索</Button>
            <Button type="primary" onClick={() => setAddOpen(true)}>+ 添加标的</Button>
          </Space>
        }
      />

      <Card size="small" className="w-full">
        <Space wrap size="middle">
          <Input.Search placeholder="代码/名称" allowClear style={{ width: 200 }} onSearch={setSearch} />
          <Select placeholder="市场" allowClear style={{ width: 120 }} onChange={setMarket} options={Object.entries(MARKET_LABELS).map(([k, v]) => ({ value: k, label: v }))} />
          <Select placeholder="类型" allowClear style={{ width: 120 }} onChange={setAssetType} options={ASSET_TYPES} />
          <Select placeholder="状态" allowClear style={{ width: 120 }} onChange={setEnabled} options={[{ value: true, label: "启用" }, { value: false, label: "禁用" }]} />
        </Space>
      </Card>

      {searchOpen && (
        <Card size="small" title="搜索标的（多数据源聚合，支持未追踪的标的）">
          <Space style={{ marginBottom: 12 }}>
            <Input.Search
              placeholder="输入名称或代码，如 宁德时代 / 300750 / 比亚迪"
              allowClear
              style={{ width: 360 }}
              onSearch={(v) => {
                setKeyword(v);
                externalSearch.refetch();
              }}
            />
            <Tooltip title={"数据源：新浪 + NeoData + WeStock；未追踪的标的可直接点右侧『添加』一键加入。"}>
              <span style={{ color: "var(--color-text-secondary)", fontSize: 12, cursor: "help" }}>ℹ️ 说明</span>
            </Tooltip>
          </Space>
          {externalSearch.isError ? (
            <QueryErrorState error={externalSearch.error} onRetry={externalSearch.refetch} />
          ) : (
            <Table
              size="small"
              loading={externalSearch.isFetching}
              rowKey={(r) => `${r.source ?? "x"}-${r.symbol}`}
              dataSource={externalSearch.data?.items ?? []}
              pagination={false}
              columns={[
                { title: "代码", dataIndex: "symbol" },
                { title: "名称", dataIndex: "name", render: (n?: string | null) => n || <span className="pnl-empty">—</span> },
                { title: "市场", dataIndex: "market", render: (m?: string | null) => (m ? MARKET_LABELS[m] ?? m : <span className="pnl-empty">—</span>) },
                { title: "类型", dataIndex: "asset_type", render: (t?: string | null) => (t ? ASSET_TYPE_LABELS[t] ?? t : <span className="pnl-empty">—</span>) },
                {
                  title: "数据源",
                  dataIndex: "source",
                  render: (s?: string) => (s ? <Tag bordered={false}>{s}</Tag> : <span className="pnl-empty">—</span>),
                },
                {
                  title: "操作",
                  key: "action",
                  align: "center",
                  width: 120,
                  render: (_, record: AssetSearchResult) => {
                    if (record.already_tracked) {
                      return <Tag color="default" bordered={false}>已添加</Tag>;
                    }
                    // 标记正在添加的 symbol，禁用按钮防止双击
                    const isAdding =
                      quickCreate.isPending && quickCreate.variables?.symbol === record.symbol;
                    return (
                      <Button
                        type="primary"
                        size="small"
                        loading={isAdding}
                        onClick={() => quickCreate.mutate(record)}
                      >
                        + 添加
                      </Button>
                    );
                  },
                },
              ]}
            />
          )}
        </Card>
      )}

      {assets.isLoading ? (
        <Skeleton active />
      ) : assets.isError ? (
        <QueryErrorState error={assets.error} onRetry={assets.refetch} />
      ) : (
        <Table size="small" rowKey="id" dataSource={assets.data?.items ?? []} columns={columns} pagination={{ total: assets.data?.page_info.total, pageSize: 50, showSizeChanger: false }} />
      )}

      <Modal
        title="添加追踪标的"
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
        width={560}
        destroyOnClose
      >
        <AddModalSearch onPick={onPickSearchResult} />
        <Divider style={{ margin: "12px 0 4px" }}>或手动填写</Divider>
        <Form
          form={form}
          layout="vertical"
          onFinish={(v) => create.mutate(v)}
          initialValues={{ asset_type: "stock", market: "sh" }}
        >
          <Form.Item name="symbol" label="代码" rules={[{ required: true }]}>
            <Input placeholder="如 sh600000 / sz300750（搜索结果会自动填入）" />
          </Form.Item>
          <Form.Item name="name" label="名称">
            <Input placeholder="搜索结果会自动填入" />
          </Form.Item>
          <Form.Item name="market" label="市场" rules={[{ required: true }]}>
            <Select options={Object.entries(MARKET_LABELS).map(([k, v]) => ({ value: k, label: v }))} />
          </Form.Item>
          <Form.Item name="asset_type" label="类型" rules={[{ required: true }]}>
            <Select options={ASSET_TYPES} />
          </Form.Item>
          <Form.Item name="tags" label="标签（逗号分隔，最多 10 个）">
            <Input />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
