import {
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Divider,
  InputNumber,
  Popconfirm,
  Row,
  Skeleton,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiClient, extractErrorMessage } from "@/api/client";
import type {
  DataSourceItem,
  DataSourcesStatus,
  DataSourceStatusItem,
  SettingsResponse,
  TaskStatusItem,
} from "@/api/types";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryErrorState } from "@/components/shared/QueryErrorState";
// StatusTag 仍被其它卡片使用，保留 import
import { StatusTag } from "@/components/shared/StatusTag";
import { TASK_LABELS } from "@/utils/constants";
import { getTaskStatusMeta } from "@/utils/format";

interface DataSourcesResponse {
  structured: DataSourceItem[];
  news: DataSourceItem[];
}

interface TaskStatusResponse {
  items: TaskStatusItem[];
}

// 数据源超时行内编辑：进入/取消/保存。
// - 初始显示"值 + 修改"按钮
// - 进入编辑后显示 InputNumber + 保存/取消
// - 保存立即 PATCH（无需回车）
function SourceTimeoutCell({
  value,
  group: _group,
  name: _name,
  isPending,
  onSave,
}: {
  value: number;
  group: string;
  name: string;
  isPending: boolean;
  onSave: (v: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<number>(value);

  // 切换行编辑时（不同数据源）重置 draft
  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  if (!editing) {
    return (
      <Space>
        <span>{value}</span>
        <Button
          size="small"
          type="link"
          style={{ padding: 0 }}
          onClick={() => { setDraft(value); setEditing(true); }}
        >
          修改
        </Button>
      </Space>
    );
  }

  return (
    <Space size={4}>
      <InputNumber
        size="small"
        min={1}
        max={120}
        value={draft}
        onChange={(v) => setDraft(typeof v === "number" ? v : 1)}
        style={{ width: 80 }}
        addonAfter="s"
      />
      <Button
        type="primary"
        size="small"
        loading={isPending}
        disabled={draft === value}
        onClick={() => { onSave(draft); setEditing(false); }}
      >
        保存
      </Button>
      <Button size="small" onClick={() => setEditing(false)}>
        取消
      </Button>
    </Space>
  );
}

function renderTaskStatus(status?: string | null) {
  const meta = getTaskStatusMeta(status);
  if (!meta) {
    return "—";
  }
  const variantMap: Record<string, "success" | "error" | "warning" | "info" | "neutral"> = {
    success: "success",
    running: "info",
    failure: "error",
    failed: "error",
    skipped: "neutral",
    pending: "warning",
  };
  return <StatusTag value={meta.label} variantMap={variantMap} labelMap={{ [meta.label]: meta.label }} />;
}

function NeoDataStatusRow({ item }: { item?: DataSourceStatusItem }) {
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

// 可编辑配置区
// 范围：scheduler.tasks.*.interval（立即生效）+ 数据源只读
// 数据源 enabled/timeout 需重启才能让 Provider registry 重建，所以暂只读
function EditableSettingsCard() {
  const queryClient = useQueryClient();

  const settings = useQuery<SettingsResponse>({
    queryKey: ["settings", "editable"],
    queryFn: async () => {
      const { data } = await apiClient.get<SettingsResponse>("/settings");
      return data;
    },
    staleTime: 30_000,
  });

  const [editingTask, setEditingTask] = useState<string | null>(null);
  const [newInterval, setNewInterval] = useState<number | null>(null);

  const updateInterval = useMutation({
    mutationFn: async ({ task, interval }: { task: string; interval: number }) => {
      await apiClient.patch("/settings", {
        updates: { [`scheduler.tasks.${task}.interval`]: interval },
      });
    },
    onSuccess: (_data, { task, interval }) => {
      message.success(`已更新 ${TASK_LABELS[task] ?? task} 频率：每 ${interval} 分钟`);
      setEditingTask(null);
      setNewInterval(null);
      queryClient.invalidateQueries({ queryKey: ["settings", "editable"] });
      queryClient.invalidateQueries({ queryKey: ["tasks", "status"] });
    },
    onError: (err) => message.error(`更新失败：${extractErrorMessage(err)}`),
  });

  const rollback = useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<SettingsResponse>("/settings/rollback");
      return data;
    },
    onSuccess: () => {
      message.success("已从备份回滚");
      queryClient.invalidateQueries({ queryKey: ["settings", "editable"] });
      queryClient.invalidateQueries({ queryKey: ["tasks", "status"] });
    },
    onError: (err) => message.error(`回滚失败：${extractErrorMessage(err)}`),
  });

  // 数据源启用/禁用/超时变更：PATCH 立即生效（后端重建 Provider）
  const updateSource = useMutation({
    mutationFn: async (params: { group: string; name: string; updates: Record<string, unknown> }) => {
      const keyPrefix = `data_sources.${params.group}.${params.name}`;
      const updates: Record<string, unknown> = {};
      for (const [field, value] of Object.entries(params.updates)) {
        updates[`${keyPrefix}.${field}`] = value;
      }
      await apiClient.patch("/settings", { updates });
    },
    onSuccess: (_data, { group, name, updates }) => {
      const fields = Object.keys(updates).map((f) => f.split(".").pop()).join(", ");
      message.success(`已更新 ${group}/${name}：${fields}（Provider 已重建）`);
      queryClient.invalidateQueries({ queryKey: ["settings", "editable"] });
      // 数据源变更可能影响定时任务下次运行（被禁用的 Provider 不再被调用）
      queryClient.invalidateQueries({ queryKey: ["tasks", "logs"] });
    },
    onError: (err, { name }) => message.error(`更新 ${name} 失败：${extractErrorMessage(err)}`),
  });

  if (settings.isLoading) return <Skeleton active />;
  if (settings.isError) {
    return <QueryErrorState error={settings.error} onRetry={settings.refetch} />;
  }

  const tasks = settings.data?.editable.scheduler.tasks ?? {};
  const sources = settings.data?.editable.sources ?? [];

  return (
    <Space direction="vertical" size="middle" className="w-full">
      <div>
        <Space style={{ marginBottom: 8 }}>
          <Typography.Text strong>采集任务频率</Typography.Text>
          <Tooltip title="点保存后立即生效（APScheduler 重注册任务）">
            <Typography.Text type="secondary" className="text-xs">ⓘ 立即生效</Typography.Text>
          </Tooltip>
        </Space>
        <Table
          size="small"
          rowKey="name"
          pagination={false}
          dataSource={Object.entries(tasks).map(([name, t]) => ({ name, ...t }))}
          columns={[
            {
              title: "任务",
              dataIndex: "name",
              render: (n: string) => TASK_LABELS[n] ?? n,
            },
            {
              title: "类型",
              dataIndex: "interval",
              width: 100,
              render: (v: number | null) =>
                v != null ? <Tag color="blue">interval</Tag> : <Tag>cron</Tag>,
            },
            {
              title: "当前值",
              key: "current",
              render: (_: unknown, r) =>
                r.interval != null ? `每 ${r.interval} 分钟` : r.cron ?? "—",
            },
            {
              title: "操作",
              key: "action",
              width: 280,
              render: (_: unknown, r) => {
                if (r.interval == null) {
                  return <Typography.Text type="secondary" className="text-xs">cron 暂不开放</Typography.Text>;
                }
                const isEditing = editingTask === r.name;
                return isEditing ? (
                  <Space>
                    <InputNumber
                      size="small"
                      min={1}
                      max={1440}
                      value={newInterval}
                      onChange={(v) => setNewInterval(typeof v === "number" ? v : null)}
                      style={{ width: 110 }}
                      addonAfter="分钟"
                    />
                    <Button
                      type="primary"
                      size="small"
                      loading={updateInterval.isPending}
                      onClick={() =>
                        newInterval != null &&
                        updateInterval.mutate({ task: r.name, interval: newInterval })
                      }
                    >
                      保存
                    </Button>
                    <Button size="small" onClick={() => { setEditingTask(null); setNewInterval(null); }}>
                      取消
                    </Button>
                  </Space>
                ) : (
                  <Button
                    size="small"
                    onClick={() => { setEditingTask(r.name); setNewInterval(r.interval); }}
                  >
                    修改
                  </Button>
                );
              },
            },
          ]}
        />
      </div>

      <div>
        <Space style={{ marginBottom: 8 }}>
          <Typography.Text strong>数据源</Typography.Text>
          <Tooltip title="启用/禁用 / 修改超时：点保存后后端立即重建 Provider 列表生效">
            <Typography.Text type="secondary" className="text-xs">ⓘ 立即生效</Typography.Text>
          </Tooltip>
        </Space>
        <Table
          size="small"
          rowKey={(r) => `${r.group}-${r.name}`}
          pagination={false}
          dataSource={sources}
          columns={[
            { title: "分组", dataIndex: "group", width: 100 },
            { title: "名称", dataIndex: "name" },
            { title: "Provider", dataIndex: "provider" },
            {
              title: "启用",
              dataIndex: "enabled",
              width: 90,
              render: (v: boolean, record) => {
                const isPending =
                  updateSource.isPending &&
                  updateSource.variables?.group === record.group &&
                  updateSource.variables?.name === record.name &&
                  "enabled" in (updateSource.variables?.updates ?? {});
                return (
                  <Switch
                    size="small"
                    checked={v}
                    disabled={isPending}
                    onChange={(checked) =>
                      updateSource.mutate({
                        group: record.group,
                        name: record.name,
                        updates: { enabled: checked },
                      })
                    }
                  />
                );
              },
            },
            {
              title: "可选",
              dataIndex: "optional",
              width: 70,
              render: (v: boolean) => (v ? "是" : "★ 必需"),
            },
            {
              title: "超时(s)",
              dataIndex: "timeout",
              width: 180,
              render: (v: number, record) => (
                <SourceTimeoutCell
                  value={v}
                  group={record.group}
                  name={record.name}
                  isPending={
                    updateSource.isPending &&
                    updateSource.variables?.group === record.group &&
                    updateSource.variables?.name === record.name &&
                    "timeout" in (updateSource.variables?.updates ?? {})
                  }
                  onSave={(newValue) =>
                    updateSource.mutate({
                      group: record.group,
                      name: record.name,
                      updates: { timeout: newValue },
                    })
                  }
                />
              ),
            },
          ]}
        />
      </div>

      <Space>
        <Popconfirm
          title="从 .bak 恢复最近一次修改？"
          description="所有未回滚的更改会丢失"
          okText="确认回滚"
          cancelText="取消"
          onConfirm={() => rollback.mutate()}
        >
          <Button danger loading={rollback.isPending}>
            ↩ 从备份回滚
          </Button>
        </Popconfirm>
      </Space>
    </Space>
  );
}

export default function SettingsPage() {
  const sources = useQuery<DataSourcesResponse>({
    queryKey: ["data-sources", "config"],
    queryFn: async () => {
      const { data } = await apiClient.get<DataSourcesResponse>("/data-sources/config");
      return data;
    },
    staleTime: 60_000,
  });

  const sourcesStatus = useQuery<DataSourcesStatus>({
    queryKey: ["data-sources", "status"],
    queryFn: async () => {
      const { data } = await apiClient.get<DataSourcesStatus>("/data-sources/status");
      return data;
    },
    staleTime: 60_000,
  });

  const tasks = useQuery<TaskStatusResponse>({
    queryKey: ["tasks", "status"],
    queryFn: async () => {
      const { data } = await apiClient.get<TaskStatusResponse>("/tasks/status");
      return data;
    },
    staleTime: 60_000,
  });

  const sourceColumns: ColumnsType<DataSourceItem> = [
    { title: "名称", dataIndex: "name", key: "name" },
    { title: "Provider", dataIndex: "provider", key: "provider" },
    { title: "类型", dataIndex: "type", key: "type" },
    {
      title: "启用",
      dataIndex: "enabled",
      key: "enabled",
      render: (enabled: boolean) => (
        <StatusTag
          value={enabled ? "是" : "否"}
          variantMap={{ 是: "success", 否: "neutral" }}
          labelMap={{ 是: "✓ 启用", 否: "✕ 禁用" }}
        />
      ),
    },
    {
      title: "可选",
      dataIndex: "optional",
      key: "optional",
      render: (optional: boolean) => (
        <StatusTag
          value={optional ? "是" : "否"}
          variantMap={{ 是: "neutral", 否: "accent" }}
          labelMap={{ 是: "可选", 否: "★ 必需" }}
        />
      ),
    },
  ];

  const neodataItem = (sourcesStatus.data?.structured ?? []).find(
    (s) => s.provider === "NeoDataProvider",
  );

  return (
    <Space direction="vertical" size={24} className="w-full">
      <PageHeader
        title="系统配置"
        subtitle="可编辑配置 + 数据源状态 + 调度任务 + NeoData token 健康"
      />

      <Card title="可编辑配置" size="small" className="w-full">
        <EditableSettingsCard />
      </Card>

      <Card title="数据源状态" size="small" className="w-full">
        {sources.isLoading ? (
          <Skeleton active />
        ) : sources.isError ? (
          <QueryErrorState error={sources.error} onRetry={sources.refetch} />
        ) : (
          <Space direction="vertical" size="middle" className="w-full">
            <Typography.Text type="secondary">结构化数据源</Typography.Text>
            <Table
              size="small"
              rowKey={(r) => `s-${r.name}`}
              dataSource={sources.data?.structured ?? []}
              columns={sourceColumns}
              pagination={false}
            />
            <Divider style={{ margin: 0 }} />
            <Typography.Text type="secondary">新闻数据源</Typography.Text>
            <Table
              size="small"
              rowKey={(r) => `n-${r.name}`}
              dataSource={sources.data?.news ?? []}
              columns={sourceColumns}
              pagination={false}
            />
            <Divider style={{ margin: 0 }} />
            <Typography.Text type="secondary">NeoData token 健康</Typography.Text>
            {sourcesStatus.isLoading ? (
              <Skeleton active />
            ) : sourcesStatus.isError ? (
              <QueryErrorState error={sourcesStatus.error} onRetry={sourcesStatus.refetch} />
            ) : (
              <NeoDataStatusRow item={neodataItem} />
            )}
          </Space>
        )}
      </Card>

      <Card title="调度任务" size="small" className="w-full">
        {tasks.isLoading ? (
          <Skeleton active />
        ) : tasks.isError ? (
          <QueryErrorState error={tasks.error} onRetry={tasks.refetch} />
        ) : (
          <Table
            size="small"
            rowKey={(r) => r.task_name}
            dataSource={tasks.data?.items ?? []}
            pagination={false}
            columns={[
              {
                title: "任务",
                dataIndex: "task_name",
                key: "task_name",
                render: (name: string) => TASK_LABELS[name] ?? name,
              },
              { title: "调度", dataIndex: "schedule", key: "schedule" },
              {
                title: "上次状态",
                dataIndex: "last_status",
                key: "last_status",
                render: renderTaskStatus,
              },
              { title: "下次执行", dataIndex: "next_run_at", key: "next_run_at" },
            ]}
          />
        )}
      </Card>

      <Card title="系统信息" size="small" className="w-full">
        <Row gutter={16}>
          <Col span={8}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="数据库">SQLite（本地文件）</Descriptions.Item>
              <Descriptions.Item label="数据存储">全部本地，不上传云端</Descriptions.Item>
              <Descriptions.Item label="AI 引擎">规则引擎 + 证据驱动</Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>
      </Card>

      <Collapse
        ghost
        items={[
          {
            key: "design-system",
            label: (
              <Typography.Text type="secondary">🎨 设计系统预览</Typography.Text>
            ),
            children: (
              <Card size="small">
                <Space direction="vertical" size="middle" className="w-full">
                  <div>
                    <Typography.Text strong>Color Tokens</Typography.Text>
                    <div className="grid grid-cols-8 gap-2 mt-2">
                      {[
                        { name: "primary", token: "var(--color-primary)" },
                        { name: "primary-soft", token: "var(--color-primary-soft)" },
                        { name: "accent", token: "var(--color-accent)" },
                        { name: "accent-soft", token: "var(--color-accent-soft)" },
                        { name: "success", token: "var(--color-success)" },
                        { name: "warning", token: "var(--color-warning)" },
                        { name: "error", token: "var(--color-error)" },
                        { name: "info", token: "var(--color-info)" },
                      ].map((c) => (
                        <div key={c.name} className="text-center">
                          <div
                            style={{
                              background: c.token,
                              width: "100%",
                              height: 36,
                              borderRadius: 6,
                              border: "1px solid var(--color-border)",
                            }}
                          />
                          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                            {c.name}
                          </Typography.Text>
                        </div>
                      ))}
                    </div>
                  </div>
                  <Divider style={{ margin: 0 }} />
                  <div>
                    <Typography.Text strong>Status Tags</Typography.Text>
                    <div className="flex gap-2 mt-2 flex-wrap">
                      {[
                        { variant: "success" as const, label: "成功", icon: "✓" },
                        { variant: "error" as const, label: "失败", icon: "✕" },
                        { variant: "warning" as const, label: "警告", icon: "!" },
                        { variant: "info" as const, label: "运行中", icon: "i" },
                        { variant: "neutral" as const, label: "已跳过", icon: "·" },
                        { variant: "accent" as const, label: "重要", icon: "★" },
                      ].map((t) => (
                        <span key={t.variant} className={`status-tag status-tag-${t.variant}`}>
                          <span className="status-icon">{t.icon}</span>
                          <span>{t.label}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                  <Divider style={{ margin: 0 }} />
                  <div>
                    <Typography.Text strong>Typography Scale</Typography.Text>
                    <div className="mt-2 space-y-1">
                      <div style={{ fontSize: 32, lineHeight: "40px", fontWeight: 700 }}>Display 32/40</div>
                      <div style={{ fontSize: 24, lineHeight: "32px", fontWeight: 700 }}>H1 24/32</div>
                      <div style={{ fontSize: 20, lineHeight: "28px", fontWeight: 600 }}>H2 20/28</div>
                      <div style={{ fontSize: 16, lineHeight: "24px", fontWeight: 600 }}>H3 16/24</div>
                      <div style={{ fontSize: 14, lineHeight: "22px" }}>Body 14/22 正文</div>
                      <div style={{ fontSize: 12, lineHeight: "18px", color: "var(--color-text-secondary)" }}>Caption 12/18 辅助</div>
                      <div className="kpi-chip-value">Metric 28/36 数字</div>
                    </div>
                  </div>
                </Space>
              </Card>
            ),
          },
        ]}
      />
    </Space>
  );
}
