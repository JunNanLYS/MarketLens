import { Card, Col, Collapse, Descriptions, Divider, Row, Skeleton, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { DataSourceItem, DataSourcesStatus, DataSourceStatusItem, TaskStatusItem } from "@/api/types";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryErrorState } from "@/components/shared/QueryErrorState";
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

function renderTaskStatus(status?: string | null) {
  const meta = getTaskStatusMeta(status);
  if (!meta) {
    return "—";
  }
  // 状态值到 variant 映射（DESIGN.md §4.5）
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

// 渲染 NeoData 单源 token 健康行
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

// 系统配置页：数据源状态 + 调度任务 + 静态系统信息 + 设计系统预览
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

  // 找到 NeoData 源（结构化列表中 provider === "NeoDataProvider"）
  const neodataItem = (sourcesStatus.data?.structured ?? []).find(
    (s) => s.provider === "NeoDataProvider",
  );

  return (
    <Space direction="vertical" size={24} className="w-full">
      <PageHeader
        title="系统配置"
        subtitle="数据源连接状态、调度任务运行情况、NeoData token 健康"
      />

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
