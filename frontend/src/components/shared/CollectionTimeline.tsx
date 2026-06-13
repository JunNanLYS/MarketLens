import { Button, Card, Empty, Skeleton, Timeline, Typography } from "antd";
import { useInfiniteQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiClient } from "@/api/client";
import type { TaskLog, PageResult } from "@/api/types";
import { TASK_LABELS } from "@/utils/constants";
import { getTaskStatusMeta } from "@/utils/format";
import { QueryErrorState } from "@/components/shared/QueryErrorState";

const { Text } = Typography;

interface CollectionTimelineProps {
  symbol?: string;
  // 单页大小：默认 20 条。视窗高度按 symbol 卡片宽度自动容纳 ~10 条 + 滚动加载。
  pageSize?: number;
}

// Task log status → Timeline 节点颜色（token 名）
function getTimelineNodeColor(status: string): string {
  if (status === "failure" || status === "error" || status === "failed") {
    return "var(--color-error)";
  }
  if (status === "success") {
    return "var(--color-success)";
  }
  if (status === "running" || status === "pending") {
    return "var(--color-info)";
  }
  return "var(--color-text-tertiary)";
}

// 采集事件时间轴：滑动视窗 + 触底加载
//
// 设计要点：
// - useInfiniteQuery 维护 pages 数组；UI 渲染时把 pages 扁平展平。
// - IntersectionObserver 监控底部 sentinel，触底自动 fetchNextPage。
// - 容器设 max-height + overflow:auto，用户感知是"卡片在长但可滚动"，
//   而非"页面一直往下长"——解决截图中 Timeline 顶到屏幕外的问题。
// - 错误事件额外展开错误摘要，点击行即可折叠。
export function CollectionTimeline({ symbol, pageSize = 20 }: CollectionTimelineProps) {
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const logs = useInfiniteQuery<PageResult<TaskLog>>({
    queryKey: ["tasks", "logs", "infinite", { page_size: pageSize }],
    initialPageParam: 1,
    queryFn: async ({ pageParam }) => {
      const { data } = await apiClient.get<PageResult<TaskLog>>("/tasks/logs", {
        params: { page: pageParam, page_size: pageSize },
      });
      return data;
    },
    getNextPageParam: (lastPage, _allPages, lastPageParam) => {
      // 后端 page_info.total 已知；超出则停
      const total = lastPage.page_info?.total ?? 0;
      const last = typeof lastPageParam === "number" ? lastPageParam : 1;
      const loaded = last * pageSize;
      return loaded < total ? last + 1 : undefined;
    },
    staleTime: 30_000,
  });

  // 触底加载：监控 sentinel，进入视口时 fetchNextPage
  // ref 模式：IntersectionObserver 只挂一次，避免 deps 含整个对象导致重连
  const fetchNextRef = useRef(logs.fetchNextPage);
  const hasNextRef = useRef(logs.hasNextPage);
  const fetchingRef = useRef(logs.isFetchingNextPage);
  fetchNextRef.current = logs.fetchNextPage;
  hasNextRef.current = logs.hasNextPage;
  fetchingRef.current = logs.isFetchingNextPage;

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const e = entries[0];
        if (e.isIntersecting && hasNextRef.current && !fetchingRef.current) {
          fetchNextRef.current();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // 展开的错误 id 用 Set 维护（保持原行为）
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // 扁平展平所有已加载的 pages
  const items = useMemo(
    () => (logs.data?.pages ?? []).flatMap((p) => p.items ?? []),
    [logs.data],
  );

  if (logs.isLoading) return <Skeleton active />;
  if (logs.isError) {
    return <QueryErrorState error={logs.error} onRetry={logs.refetch} />;
  }

  if (items.length === 0) {
    return (
      <Card size="small" title={symbol ? `${symbol} 采集历史` : "采集历史"}>
        <Empty description="暂无采集记录" />
      </Card>
    );
  }

  return (
    <Card
      size="small"
      title={symbol ? `${symbol} 采集历史` : "采集历史"}
      className="w-full"
      // 卡片 body 改为可滚动容器，限制最大高度为视口的 60%（约 540px）。
      // Timeline 内容超出后内部滚动，不再顶到屏幕外。
      styles={{
        body: {
          maxHeight: "60vh",
          overflowY: "auto",
          paddingRight: 8,
        },
      }}
    >
      <Timeline
        items={items.map((log) => {
          const meta = getTaskStatusMeta(log.status);
          const isFailure =
            log.status === "failure" || log.status === "error" || log.status === "failed";
          const label = TASK_LABELS[log.task_name] ?? log.task_name;
          const time = log.started_at ? dayjs(log.started_at).format("MM-DD HH:mm") : "-";
          const expanded = expandedIds.has(log.id);
          const duration =
            log.started_at && log.finished_at
              ? dayjs(log.finished_at).diff(dayjs(log.started_at), "second")
              : null;

          const children = (
            <div>
              <Text strong>{label}</Text>
              <Text type="secondary" className="ml-2 text-xs">{time}</Text>
              {meta && (
                <span
                  className="ml-2 text-xs px-1.5 py-0.5 rounded"
                  style={{
                    color: getTimelineNodeColor(log.status),
                    background: "var(--color-bg-base)",
                  }}
                >
                  {meta.label}
                </span>
              )}
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
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      toggleExpand(log.id);
                    }
                  }}
                >
                  <Text
                    type="danger"
                    className="text-xs"
                    style={{ color: "var(--color-error)" }}
                  >
                    {expanded ? "▼ 收起错误" : "▶ 查看错误"}
                  </Text>
                  {expanded && (
                    <div
                      className="mt-1 p-2 rounded text-xs"
                      style={{
                        background: "var(--color-error-soft)",
                        color: "var(--color-error)",
                      }}
                    >
                      {log.error_message}
                    </div>
                  )}
                </div>
              )}
            </div>
          );

          return {
            color: getTimelineNodeColor(log.status),
            children,
          };
        })}
      />

      {/* 触底 sentinel + 加载状态 */}
      <div ref={sentinelRef} style={{ height: 1 }} />
      <div className="text-center py-2">
        {logs.isFetchingNextPage ? (
          <Text type="secondary" className="text-xs">加载中…</Text>
        ) : logs.hasNextPage ? (
          <Button type="link" size="small" onClick={() => logs.fetchNextPage()}>
            加载更多
          </Button>
        ) : (
          <Text type="secondary" className="text-xs">已加载全部 {items.length} 条</Text>
        )}
      </div>
    </Card>
  );
}
