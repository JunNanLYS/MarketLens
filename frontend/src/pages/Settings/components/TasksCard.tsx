import { Card, Skeleton, Table } from "antd";
import type { TaskStatusItem } from "@/api/types";
import { QueryErrorState } from "@/components/shared/QueryErrorState";
import { StatusTag } from "@/components/shared/StatusTag";
import { TASK_LABELS } from "@/utils/constants";
import { getTaskStatusMeta } from "@/utils/format";

interface TaskStatusResponse {
  items: TaskStatusItem[];
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

// 调度任务卡：APScheduler 任务状态表。
// 父级 SettingsPage useQuery 提供 tasks + 状态回调，子组件纯展示。
interface TasksCardProps {
  tasks?: TaskStatusResponse;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
}

export function TasksCard({ tasks, isLoading, isError, error, refetch }: TasksCardProps) {
  return (
    <Card title="调度任务" size="small" className="w-full">
      {isLoading ? (
        <Skeleton active />
      ) : isError ? (
        <QueryErrorState error={error} onRetry={refetch} />
      ) : (
        <Table
          size="small"
          rowKey={(r) => r.task_name}
          dataSource={tasks?.items ?? []}
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
  );
}
