import { Card, Col, Descriptions, Divider, Row, Skeleton, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQuery } from "@tanstack/react-query";
import { apiClient, extractErrorMessage } from "@/api/client";
import type { DataSourceItem, TaskStatusItem } from "@/api/types";
import { TASK_LABELS } from "@/utils/constants";

interface DataSourcesResponse {
  structured: DataSourceItem[];
  news: DataSourceItem[];
}

interface TaskStatusResponse {
  items: TaskStatusItem[];
}

// 系统配置页：数据源状态 + 调度任务 + 静态系统信息（对应原 Streamlit settings.py）
export default function SettingsPage() {
  const sources = useQuery<DataSourcesResponse>({
    queryKey: ["data-sources", "config"],
    queryFn: async () => {
      const { data } = await apiClient.get<DataSourcesResponse>("/data-sources/config");
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
        <Tag color={enabled ? "green" : "default"}>{enabled ? "是" : "否"}</Tag>
      ),
    },
    {
      title: "可选",
      dataIndex: "optional",
      key: "optional",
      render: (optional: boolean) => (optional ? <Tag>是</Tag> : <Tag color="blue">必需</Tag>),
    },
  ];

  return (
    <Space direction="vertical" size="large" className="w-full">
      <Typography.Title level={3}>系统配置</Typography.Title>

      <Card title="数据源状态" size="small">
        {sources.isLoading ? (
          <Skeleton active />
        ) : sources.isError ? (
          <Typography.Text type="danger">
            加载失败：{extractErrorMessage(sources.error)}
          </Typography.Text>
        ) : (
          <Space direction="vertical" className="w-full">
            <Typography.Text type="secondary">结构化数据源</Typography.Text>
            <Table
              size="small"
              rowKey={(r) => `s-${r.name}`}
              dataSource={sources.data?.structured ?? []}
              columns={sourceColumns}
              pagination={false}
            />
            <Divider />
            <Typography.Text type="secondary">新闻数据源</Typography.Text>
            <Table
              size="small"
              rowKey={(r) => `n-${r.name}`}
              dataSource={sources.data?.news ?? []}
              columns={sourceColumns}
              pagination={false}
            />
          </Space>
        )}
      </Card>

      <Card title="调度任务" size="small">
        {tasks.isLoading ? (
          <Skeleton active />
        ) : tasks.isError ? (
          <Typography.Text type="danger">
            加载失败：{extractErrorMessage(tasks.error)}
          </Typography.Text>
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
                render: (status?: string | null) =>
                  status ? <Tag color={status === "success" ? "green" : "red"}>{status}</Tag> : "-",
              },
              { title: "下次执行", dataIndex: "next_run_at", key: "next_run_at" },
            ]}
          />
        )}
      </Card>

      <Card title="系统信息" size="small">
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
    </Space>
  );
}
