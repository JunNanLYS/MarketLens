import { Button, Card, Col, DatePicker, Form, Input, InputNumber, Modal, Row, Select, Skeleton, Space, Statistic, Table, Tabs, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import dayjs, { Dayjs } from "dayjs";
import { apiClient, extractErrorMessage } from "@/api/client";
import type { Account, PageResult, Position, RealizedPnlItem, Transaction } from "@/api/types";
import { confirmDelete } from "@/components/shared/ConfirmDelete";
import { PnlDisplay } from "@/components/shared/PnlDisplay";
import { formatNumber } from "@/utils/format";

interface CreateAccountForm {
  name: string;
  broker?: string;
  currency: string;
  notes?: string;
}

interface CreateTransactionForm {
  account_id: number;
  symbol: string;
  type: string;
  quantity: number;
  price: number;
  fee?: number;
  trade_date: Dayjs;
  notes?: string;
}

// 投资组合：3 个 Tab（持仓总览 / 交易记录 / 账户管理）
export default function PortfolioPage() {
  return (
    <Space direction="vertical" size="large" className="w-full">
      <Typography.Title level={3}>投资组合</Typography.Title>
      <Card>
        <Tabs
          items={[
            { key: "positions", label: "持仓总览", children: <PositionsTab /> },
            { key: "transactions", label: "交易记录", children: <TransactionsTab /> },
            { key: "accounts", label: "账户管理", children: <AccountsTab /> },
          ]}
        />
      </Card>
    </Space>
  );
}

function PositionsTab() {
  const positions = useQuery<Position[]>({
    queryKey: ["positions"],
    queryFn: async () => (await apiClient.get<Position[]>("/positions")).data,
    staleTime: 15_000,
  });

  const realized = useQuery<{ items: RealizedPnlItem[]; total: number }>({
    queryKey: ["positions", "realized-pnl"],
    queryFn: async () => (await apiClient.get("/positions/realized-pnl")).data,
    staleTime: 15_000,
  });

  const totalValue = (positions.data ?? []).reduce((s, p) => s + (p.market_value ?? 0), 0);
  const totalUnrealized = (positions.data ?? []).reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0);
  const totalRealized = (realized.data?.items ?? []).reduce((s, p) => s + p.realized_pnl, 0);

  const columns: ColumnsType<Position> = [
    { title: "代码", dataIndex: "symbol", key: "symbol" },
    { title: "名称", dataIndex: "name", key: "name" },
    { title: "账户", dataIndex: "account_id", key: "account_id" },
    { title: "数量", dataIndex: "total_qty", key: "total_qty" },
    { title: "均价", dataIndex: "avg_cost", key: "avg_cost", render: (v: number) => formatNumber(v) },
    { title: "市值", dataIndex: "market_value", key: "market_value", render: (v?: number) => formatNumber(v) },
    { title: "浮盈亏", dataIndex: "unrealized_pnl", key: "unrealized_pnl", render: (v?: number) => <PnlDisplay value={v} /> },
    { title: "浮盈亏%", dataIndex: "unrealized_pnl_pct", key: "unrealized_pnl_pct", render: (v?: number) => <PnlDisplay value={v} /> },
  ];

  return (
    <Space direction="vertical" size="middle" className="w-full">
      <Row gutter={16}>
        <Col span={8}><Statistic title="总市值" value={totalValue} precision={2} /></Col>
        <Col span={8}><Statistic title="总浮盈亏" value={totalUnrealized} precision={2} /></Col>
        <Col span={8}><Statistic title="总已实现盈亏" value={totalRealized} precision={2} /></Col>
      </Row>
      {positions.isLoading ? <Skeleton active /> : (
        <Table
          size="small"
          rowKey={(r) => `position-${r.account_id}-${r.symbol}`}
          dataSource={positions.data ?? []}
          columns={columns}
          pagination={false}
        />
      )}
      <Card size="small" title="已实现盈亏">
        <Table
          size="small"
          rowKey={(r) => `realized-${r.account_id}-${r.symbol}`}
          dataSource={realized.data?.items ?? []}
          pagination={false}
          columns={[
            { title: "账户", dataIndex: "account_id" },
            { title: "代码", dataIndex: "symbol" },
            { title: "卖出数量", dataIndex: "total_sell_qty" },
            { title: "已实现盈亏", dataIndex: "realized_pnl", render: (v: number) => <PnlDisplay value={v} /> },
          ]}
        />
      </Card>
    </Space>
  );
}

function TransactionsTab() {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [form] = Form.useForm<CreateTransactionForm>();

  const accounts = useQuery<Account[]>({
    queryKey: ["accounts"],
    queryFn: async () => (await apiClient.get<Account[]>("/accounts")).data,
    staleTime: 15_000,
  });

  const txs = useQuery<PageResult<Transaction>>({
    queryKey: ["transactions"],
    queryFn: async () => (await apiClient.get<PageResult<Transaction>>("/transactions", { params: { page: 1, page_size: 50 } })).data,
    staleTime: 15_000,
  });

  const create = useMutation({
    mutationFn: async (v: CreateTransactionForm) => {
      await apiClient.post("/transactions", { ...v, trade_date: v.trade_date.format("YYYY-MM-DD") });
    },
    onSuccess: () => {
      message.success("已添加");
      setAddOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["positions"] });
    },
    onError: (err) => message.error(`添加失败：${extractErrorMessage(err)}`),
  });

  const remove = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/transactions/${id}`);
    },
    onSuccess: () => {
      message.success("已删除");
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["positions"] });
    },
    onError: (err) => message.error(`删除失败：${extractErrorMessage(err)}`),
  });

  const columns: ColumnsType<Transaction> = [
    { title: "日期", dataIndex: "trade_date", key: "trade_date" },
    { title: "代码", dataIndex: "symbol", key: "symbol" },
    { title: "类型", dataIndex: "type", key: "type", render: (t: string) => <Tag>{t}</Tag> },
    { title: "数量", dataIndex: "quantity", key: "quantity" },
    { title: "价格", dataIndex: "price", key: "price", render: (v: number) => formatNumber(v) },
    { title: "手续费", dataIndex: "fee", key: "fee" },
    {
      title: "操作",
      key: "actions",
      render: (_, r) => (
        <Button danger size="small" onClick={() => confirmDelete({ onConfirm: () => remove.mutateAsync(r.id) })}>
          删除
        </Button>
      ),
    },
  ];

  return (
    <Space direction="vertical" className="w-full">
      <Button type="primary" onClick={() => setAddOpen(true)}>添加交易</Button>
      {txs.isLoading ? <Skeleton active /> : (
        <Table size="small" rowKey="id" dataSource={txs.data?.items ?? []} columns={columns} pagination={false} />
      )}

      <Modal
        title="添加交易"
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => create.mutate(v)} initialValues={{ type: "buy", trade_date: dayjs() }}>
          <Form.Item name="account_id" label="账户" rules={[{ required: true }]}>
            <Select options={(accounts.data ?? []).map((a) => ({ value: a.id, label: a.name }))} />
          </Form.Item>
          <Form.Item name="symbol" label="代码" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="type" label="类型" rules={[{ required: true }]}>
            <Select options={[
              { value: "buy", label: "买入" },
              { value: "sell", label: "卖出" },
              { value: "dividend", label: "分红" },
              { value: "split", label: "拆股" },
            ]} />
          </Form.Item>
          <Form.Item name="quantity" label="数量" rules={[{ required: true }]} extra="A 股按 1 手 = 100 股，ETF/基金按份">
            <InputNumber style={{ width: "100%" }} min={0} step={1} />
          </Form.Item>
          <Form.Item name="price" label="价格" rules={[{ required: true }]} extra="每股/份成交价">
            <InputNumber style={{ width: "100%" }} min={0} step={0.01} />
          </Form.Item>
          <Form.Item name="fee" label="手续费">
            <InputNumber style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="trade_date" label="交易日期" rules={[{ required: true }]}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

function AccountsTab() {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [form] = Form.useForm<CreateAccountForm>();

  const accounts = useQuery<Account[]>({
    queryKey: ["accounts"],
    queryFn: async () => (await apiClient.get<Account[]>("/accounts")).data,
    staleTime: 15_000,
  });

  const create = useMutation({
    mutationFn: async (v: CreateAccountForm) => {
      await apiClient.post("/accounts", v);
    },
    onSuccess: () => {
      message.success("已添加");
      setAddOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (err) => message.error(`添加失败：${extractErrorMessage(err)}`),
  });

  const remove = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/accounts/${id}`);
    },
    onSuccess: () => {
      message.success("已删除");
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (err) => message.error(`删除失败：${extractErrorMessage(err)}`),
  });

  const columns: ColumnsType<Account> = [
    { title: "名称", dataIndex: "name", key: "name" },
    { title: "券商", dataIndex: "broker", key: "broker" },
    { title: "币种", dataIndex: "currency", key: "currency" },
    { title: "备注", dataIndex: "notes", key: "notes" },
    {
      title: "操作",
      key: "actions",
      render: (_, r) => (
        <Button danger size="small" onClick={() => confirmDelete({ title: "确认删除账户", content: `将删除账户 ${r.name}`, onConfirm: () => remove.mutateAsync(r.id) })}>
          删除
        </Button>
      ),
    },
  ];

  return (
    <Space direction="vertical" className="w-full">
      <Button type="primary" onClick={() => setAddOpen(true)}>添加账户</Button>
      {accounts.isLoading ? <Skeleton active /> : (
        <Table size="small" rowKey="id" dataSource={accounts.data ?? []} columns={columns} pagination={false} />
      )}

      <Modal
        title="添加账户"
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => create.mutate(v)} initialValues={{ currency: "CNY" }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="broker" label="券商">
            <Input />
          </Form.Item>
          <Form.Item name="currency" label="币种" rules={[{ required: true }]}>
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
