import { Button, Card, Form, Input, Modal, Select, Skeleton, Space, Switch, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiClient, extractErrorMessage } from "@/api/client";
import type { PageResult, TrackedAsset } from "@/api/types";
import { MARKET_LABELS } from "@/utils/constants";
import { confirmDelete } from "@/components/shared/ConfirmDelete";
import { PnlDisplay } from "@/components/shared/PnlDisplay";
import { formatNumber } from "@/utils/format";

interface SearchResult {
  symbol: string;
  name: string;
  market?: string;
  asset_type?: string;
}

const ASSET_TYPES = [
  { value: "stock", label: "股票" },
  { value: "etf", label: "ETF" },
  { value: "index", label: "指数" },
];

interface AddAssetForm {
  symbol: string;
  name?: string;
  market: string;
  asset_type: string;
  tags?: string;
  notes?: string;
}

// 追踪标的：列表 + 启用/禁用 + 删除 + 添加 + 外部搜索
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

  const externalSearch = useQuery<{ items: SearchResult[]; total: number }>({
    queryKey: ["assets", "search", keyword],
    queryFn: async () => {
      const { data } = await apiClient.get("/assets/search", { params: { keyword, market } });
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
      render: (m?: string) => (m ? <Tag>{MARKET_LABELS[m] ?? m}</Tag> : "-"),
    },
    { title: "类型", dataIndex: "asset_type", key: "asset_type" },
    {
      title: "最新价",
      dataIndex: "latest_price",
      key: "latest_price",
      render: (v?: number | null) => formatNumber(v),
    },
    {
      title: "涨跌幅",
      dataIndex: "latest_change_pct",
      key: "latest_change_pct",
      render: (v?: number | null) => <PnlDisplay value={v} />,
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

  return (
    <Space direction="vertical" size="large" className="w-full">
      <Typography.Title level={3}>追踪标的</Typography.Title>

      <Card size="small">
        <Space wrap>
          <Input.Search placeholder="代码/名称" allowClear style={{ width: 200 }} onSearch={setSearch} />
          <Select placeholder="市场" allowClear style={{ width: 120 }} onChange={setMarket} options={Object.entries(MARKET_LABELS).map(([k, v]) => ({ value: k, label: v }))} />
          <Select placeholder="类型" allowClear style={{ width: 120 }} onChange={setAssetType} options={ASSET_TYPES} />
          <Select placeholder="状态" allowClear style={{ width: 120 }} onChange={setEnabled} options={[{ value: true, label: "启用" }, { value: false, label: "禁用" }]} />
          <Button type="primary" onClick={() => setAddOpen(true)}>添加</Button>
          <Button onClick={() => setSearchOpen((v) => !v)}>外部搜索</Button>
        </Space>
      </Card>

      {searchOpen && (
        <Card size="small" title="搜索外部标的">
          <Space style={{ marginBottom: 12 }}>
            <Input.Search placeholder="关键词" allowClear style={{ width: 240 }} onSearch={(v) => { setKeyword(v); externalSearch.refetch(); }} />
          </Space>
          <Table
            size="small"
            loading={externalSearch.isFetching}
            rowKey={(r) => `${r.symbol}-${r.market ?? ""}`}
            dataSource={externalSearch.data?.items ?? []}
            pagination={false}
            columns={[
              { title: "代码", dataIndex: "symbol" },
              { title: "名称", dataIndex: "name" },
              { title: "市场", dataIndex: "market" },
              {
                title: "操作",
                render: (_, record) => (
                  <Button
                    size="small"
                    onClick={() =>
                      create.mutate({
                        symbol: record.symbol,
                        name: record.name,
                        market: record.market ?? "us",
                        asset_type: record.asset_type ?? "stock",
                      })
                    }
                  >
                    添加
                  </Button>
                ),
              },
            ]}
          />
        </Card>
      )}

      {assets.isLoading ? (
        <Skeleton active />
      ) : assets.isError ? (
        <Card><Typography.Text type="danger">加载失败：{extractErrorMessage(assets.error)}</Typography.Text></Card>
      ) : (
        <Table size="small" rowKey="id" dataSource={assets.data?.items ?? []} columns={columns} pagination={{ total: assets.data?.page_info.total, pageSize: 50, showSizeChanger: false }} />
      )}

      <Modal
        title="添加追踪标的"
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => create.mutate(v)} initialValues={{ asset_type: "stock", market: "sh" }}>
          <Form.Item name="symbol" label="代码" rules={[{ required: true }]}>
            <Input placeholder="如 sh600000" />
          </Form.Item>
          <Form.Item name="name" label="名称">
            <Input />
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
