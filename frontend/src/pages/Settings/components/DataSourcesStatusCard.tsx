import { Card, Divider, Skeleton, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  DataSourceItem,
  DataSourcesStatus,
} from "@/api/types";
import { QueryErrorState } from "@/components/shared/QueryErrorState";
import { StatusTag } from "@/components/shared/StatusTag";
import { NeoDataStatusRow } from "./NeoDataStatusRow";

interface DataSourcesResponse {
  structured: DataSourceItem[];
  news: DataSourceItem[];
}

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

// 数据源状态卡：结构化 + 新闻两张表 + NeoData token 健康。
// 接收 sourcesStatus 作为 prop（由父级 SettingsPage useQuery 提供），避免重复查询。
interface DataSourcesStatusCardProps {
  sourcesStatus?: DataSourcesStatus;
  isLoadingStatus: boolean;
  isErrorStatus: boolean;
  statusError: unknown;
  refetchStatus: () => void;
}

export function DataSourcesStatusCard({
  sourcesStatus,
  isLoadingStatus,
  isErrorStatus,
  statusError,
  refetchStatus,
}: DataSourcesStatusCardProps) {
  const sources = useQuery<DataSourcesResponse>({
    queryKey: ["data-sources", "config"],
    queryFn: async () => {
      const { data } = await apiClient.get<DataSourcesResponse>("/data-sources/config");
      return data;
    },
    staleTime: 60_000,
  });

  const neodataItem = (sourcesStatus?.structured ?? []).find(
    (s) => s.provider === "NeoDataProvider",
  );

  return (
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
          {isLoadingStatus ? (
            <Skeleton active />
          ) : isErrorStatus ? (
            <QueryErrorState error={statusError} onRetry={refetchStatus} />
          ) : (
            <NeoDataStatusRow item={neodataItem} />
          )}
        </Space>
      )}
    </Card>
  );
}
