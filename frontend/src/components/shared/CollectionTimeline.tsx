import { Card, Empty, Skeleton, Timeline, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { apiClient } from "@/api/client";
import type { TaskLog, PageResult } from "@/api/types";
import { TASK_LABELS } from "@/utils/constants";
import { getTaskStatusMeta } from "@/utils/format";

const { Text } = Typography;

interface CollectionTimelineProps {
  /** 可选 symbol，暂用于标题展示；API 不支持按 symbol 过滤 */
  symbol?: string;
}

// 采集事件时间轴：展示任务运行日志，失败事件标红 + 展开错误摘要
export function CollectionTimeline({ symbol }: CollectionTimelineProps) {
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const logs = useQuery<PageResult<TaskLog>>({
    queryKey: ["tasks", "logs", { page: 1, page_size: 50 }],
    queryFn: async () => {
      const { data } = await apiClient.get<PageResult<TaskLog>>("/tasks/logs", {
        params: { page: 1, page_size: 50 },
      });
      return data;
    },
    staleTime: 60_000,
  });

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (logs.isLoading) return <Skeleton active />;
  if (logs.isError) {
    return <Card size="small"><Text type="danger">加载失败</Text></Card>;
  }

  const items = logs.data?.items ?? [];
  if (items.length === 0) {
    return <Empty description="暂无采集记录" />;
  }

  return (
    <Card
      size="small"
      title={symbol ? `${symbol} 采集历史` : "采集历史"}
      className="w-full"
    >
      <Timeline
        items={items.map((log) => {
          const meta = getTaskStatusMeta(log.status);
          const isFailure = log.status === "failure" || log.status === "error" || log.status === "failed";
          const label = TASK_LABELS[log.task_name] ?? log.task_name;
          const time = log.started_at ? dayjs(log.started_at).format("MM-DD HH:mm") : "-";
          const expanded = expandedIds.has(log.id);
          const duration = log.started_at && log.finished_at
            ? dayjs(log.finished_at).diff(dayjs(log.started_at), "second")
            : null;

          const children = (
            <div>
              <Text strong>{label}</Text>
              <Text type="secondary" className="ml-2 text-xs">{time}</Text>
              {log.affected_assets != null && log.affected_assets > 0 && (
                <Text type="secondary" className="ml-2 text-xs">{log.affected_assets} 标的</Text>
              )}
              {duration != null && (
                <Text type="secondary" className="ml-2 text-xs">{duration}s</Text>
              )}
              {isFailure && log.error_message && (
                <div
                  className="mt-1 cursor-pointer"
                  onClick={() => toggleExpand(log.id)}
                >
                  <Text type="danger" className="text-xs">
                    {expanded ? "▼ 收起错误" : "▶ 查看错误"}
                  </Text>
                  {expanded && (
                    <div className="mt-1 p-2 rounded text-xs" style={{ background: "var(--color-bg-layout)", color: "var(--color-error)" }}>
                      {log.error_message}
                    </div>
                  )}
                </div>
              )}
            </div>
          );

          return {
            color: isFailure ? "red" : meta?.color ?? "gray",
            children,
          };
        })}
      />
    </Card>
  );
}