import { Button, Card, Col, Row, Select, Skeleton, Space, Table, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import dayjs from "dayjs";
import { apiClient, extractErrorMessage } from "@/api/client";
import type { TaskLog, TaskStatusItem } from "@/api/types";
import { MotionCard } from "@/components/shared/MotionCard";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryErrorState } from "@/components/shared/QueryErrorState";
import { StatusTag } from "@/components/shared/StatusTag";
import { TASK_LABELS } from "@/utils/constants";
import { getTaskStatusMeta } from "@/utils/format";

interface TaskStatusResponse {
  items: TaskStatusItem[];
}

interface TaskLogsResponse {
  items: TaskLog[];
  page_info: { total: number };
}

interface LogsFilter {
  task_name?: string;
  status?: string;
}

const LOG_STATUS_OPTIONS = [
  { value: "success", label: "成功" },
  { value: "failure", label: "失败" },
  { value: "skipped", label: "已跳过" },
];

const STATUS_VARIANT_MAP: Record<string, "success" | "error" | "warning" | "info" | "neutral"> = {
  success: "success",
  running: "info",
  failure: "error",
  failed: "error",
  skipped: "neutral",
  pending: "warning",
};

function renderTaskStatusTag(status?: string | null) {
  const meta = getTaskStatusMeta(status);
  if (!meta) {
    return <span className="pnl-empty">—</span>;
  }
  return (
    <StatusTag
      value={meta.label}
      variantMap={{ [meta.label]: STATUS_VARIANT_MAP[status ?? ""] ?? "neutral" }}
      labelMap={{ [meta.label]: meta.label }}
    />
  );
}

// 任务状态：手动触发 + 日志筛选
export default function TaskStatusPage() {
  const queryClient = useQueryClient();
  const [logsFilter, setLogsFilter] = useState<LogsFilter>({});

  const status = useQuery<TaskStatusResponse>({
    queryKey: ["tasks", "status"],
    queryFn: async () => {
      const { data } = await apiClient.get<TaskStatusResponse>("/tasks/status");
      return data;
    },
    staleTime: 15_000,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return items[0]?.last_status === "running" ? 3000 : false;
    },
  });

  const logs = useQuery<TaskLogsResponse>({
    queryKey: ["tasks", "logs", logsFilter],
    queryFn: async () => {
      const { data } = await apiClient.get<TaskLogsResponse>("/tasks/logs", {
        params: { ...logsFilter, page: 1, page_size: 20 },
      });
      return data;
    },
    staleTime: 15_000,
  });

  const trigger = useMutation({
    mutationFn: async (taskName: string) => {
      await apiClient.post(`/tasks/trigger/${taskName}`);
    },
    onSuccess: (_data, taskName) => {
      message.success(`已触发 ${TASK_LABELS[taskName] ?? taskName}`);
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: (err) => {
      message.error(`触发失败：${extractErrorMessage(err)}`);
    },
  });

  const logColumns: ColumnsType<TaskLog> = [
    { title: "任务", dataIndex: "task_name", key: "task_name", render: (n: string) => TASK_LABELS[n] ?? n },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (statusValue: string) => renderTaskStatusTag(statusValue),
    },
    { title: "影响标的", dataIndex: "affected_assets", key: "affected_assets" },
    { title: "开始时间", dataIndex: "started_at", key: "started_at", render: (v: string) => dayjs(v).format("YYYY-MM-DD HH:mm:ss") },
    { title: "结束时间", dataIndex: "finished_at", key: "finished_at", render: (v?: string) => v ? dayjs(v).format("HH:mm:ss") : "-" },
  ];

  return (
    <Space direction="vertical" size={24} className="w-full">
      <PageHeader
        title="任务状态"
        subtitle="手动触发调度任务、查看运行历史"
      />

      {status.isLoading ? (
        <Skeleton active />
      ) : status.isError ? (
        <QueryErrorState error={status.error} onRetry={status.refetch} />
      ) : (
        <Row gutter={[16, 16]}>
          {(status.data?.items ?? []).map((t, idx) => (
            <Col key={t.task_name} xs={24} sm={12} md={8} lg={6}>
              <MotionCard delay={Math.min(idx * 0.05, 0.3)}>
                <Card
                  size="small"
                  className="card-hoverable h-full"
                  title={TASK_LABELS[t.task_name] ?? t.task_name}
                  extra={
                    <Button
                      size="small"
                      type="primary"
                      loading={trigger.isPending && trigger.variables === t.task_name}
                      onClick={() => trigger.mutate(t.task_name)}
                    >
                      触发
                    </Button>
                  }
                >
                  <Space direction="vertical" size={4}>
                    <Typography.Text type="secondary" className="text-xs">
                      {t.description ?? t.schedule ?? "—"}
                    </Typography.Text>
                    <Typography.Text className="text-xs">
                      上次：{t.last_run_at ? dayjs(t.last_run_at).format("MM-DD HH:mm") : "—"}
                    </Typography.Text>
                    {t.last_status && renderTaskStatusTag(t.last_status)}
                  </Space>
                </Card>
              </MotionCard>
            </Col>
          ))}
        </Row>
      )}

      <Card title="运行日志" size="small" className="w-full">
        <Space style={{ marginBottom: 12 }} wrap>
          <Select
            placeholder="任务"
            allowClear
            style={{ width: 160 }}
            value={logsFilter.task_name}
            onChange={(v) => setLogsFilter((f) => ({ ...f, task_name: v }))}
            options={Object.entries(TASK_LABELS).map(([k, v]) => ({ value: k, label: v }))}
          />
          <Select
            placeholder="状态"
            allowClear
            style={{ width: 120 }}
            value={logsFilter.status}
            onChange={(v) => setLogsFilter((f) => ({ ...f, status: v }))}
            options={LOG_STATUS_OPTIONS}
          />
        </Space>
        <Table
          size="small"
          rowKey="id"
          loading={logs.isLoading}
          dataSource={logs.data?.items ?? []}
          columns={logColumns}
          pagination={false}
          expandable={{
            expandedRowRender: (record) => (
              <Typography.Text type="secondary">
                {record.error_message ?? "无错误"}
              </Typography.Text>
            ),
          }}
        />
        {logs.isError ? <QueryErrorState error={logs.error} onRetry={logs.refetch} /> : null}
      </Card>
    </Space>
  );
}
