import { Card, Space } from "antd";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { DataSourcesStatus, TaskStatusItem } from "@/api/types";
import { PageHeader } from "@/components/shared/PageHeader";
import { DataSourcesStatusCard } from "./components/DataSourcesStatusCard";
import { EditableSettingsCard } from "./components/EditableSettingsCard";
import { SystemInfoCard } from "./components/SystemInfoCard";
import { TasksCard } from "./components/TasksCard";

interface TaskStatusResponse {
  items: TaskStatusItem[];
}

// SettingsPage：系统配置主页。
// 4 张卡片由子组件承担，本文件仅负责 useQuery + 卡片组合。
// - EditableSettingsCard 自管 useQuery + 3 个 useMutation
// - DataSourcesStatusCard 自管 sources config query，父级传入 sourcesStatus
// - TasksCard 自管 fallback query
// - SystemInfoCard 纯静态
export default function SettingsPage() {
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

  return (
    <Space direction="vertical" size={24} className="w-full">
      <PageHeader
        title="系统配置"
        subtitle="可编辑配置 + 数据源状态 + 调度任务 + NeoData token 健康"
      />

      <Card title="可编辑配置" size="small" className="w-full">
        <EditableSettingsCard />
      </Card>

      <DataSourcesStatusCard
        sourcesStatus={sourcesStatus.data}
        isLoadingStatus={sourcesStatus.isLoading}
        isErrorStatus={sourcesStatus.isError}
        statusError={sourcesStatus.error}
        refetchStatus={sourcesStatus.refetch}
      />

      <TasksCard
        tasks={tasks.data}
        isLoading={tasks.isLoading}
        isError={tasks.isError}
        error={tasks.error}
        refetch={tasks.refetch}
      />

      <SystemInfoCard />
    </Space>
  );
}
