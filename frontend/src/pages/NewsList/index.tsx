import { Card, Empty, Input, Select, Skeleton, Space, Tag, Tooltip, Typography } from "antd";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import dayjs from "dayjs";
import { apiClient } from "@/api/client";
import type { NewsItem, PageResult } from "@/api/types";
import { SENTIMENT_LABELS } from "@/utils/constants";
import { MotionCard } from "@/components/shared/MotionCard";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryErrorState } from "@/components/shared/QueryErrorState";
import { StatusTag } from "@/components/shared/StatusTag";

interface NewsFilters {
  symbol: string;
  days: number;
  sentiment?: "positive" | "negative" | "neutral";
}

// 渲染 "AI 已评分" 角标
function ScoredTag({ item }: { item: NewsItem }) {
  if (item.ai_scored) {
    const conf = typeof item.confidence === "number" ? item.confidence : null;
    const label = conf !== null ? `AI 评分 · ${conf.toFixed(2)}` : "AI 已评分";
    const reasonTip = item.sentiment_reason || "无理由";
    return (
      <Tooltip title={reasonTip}>
        <StatusTag
          value={label}
          variantMap={{ [label]: "info" }}
          labelMap={{ [label]: `🤖 ${label}` }}
        />
      </Tooltip>
    );
  }
  return (
    <Tooltip title="该新闻采集时 DeepSeek 未出分（迁移前数据或本次分析失败），sentiment 字段取自原始数据源">
      <StatusTag
        value="未评分"
        variantMap={{ 未评分: "neutral" }}
        labelMap={{ 未评分: "○ 未评分" }}
      />
    </Tooltip>
  );
}

// 新闻列表：滑动视窗 + 触底加载
// - useInfiniteQuery 维护 pages；UI 渲染时扁平展平
// - filter 变化时通过 queryKey 自动重置（不需要手动 reset）
// - 容器 max-height 60vh，超出滚动；不再"无限往下长"
const PAGE_SIZE = 20;

export default function NewsListPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<NewsFilters>({ symbol: "", days: 7 });
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  // 滚动容器 ref —— IntersectionObserver 必须以这个容器为 root，
  // 否则会拿默认 viewport 作 root，sentinel 被 60vh 容器裁掉但几何位置仍在
  // viewport 内 → 永远报告 intersecting=true → 永远不再 fire 新事件 → 触底加载失效
  const scrollRootRef = useRef<HTMLDivElement | null>(null);

  const news = useInfiniteQuery<PageResult<NewsItem>, Error>({
    // 把 filter 放进 queryKey 触发自动重置（页码从 1 重新开始）
    queryKey: ["news", "infinite", filters],
    initialPageParam: 1,
    queryFn: async ({ pageParam }) => {
      const { data } = await apiClient.get<PageResult<NewsItem>>("/news", {
        params: {
          symbol: filters.symbol || undefined,
          days: filters.days,
          sentiment: filters.sentiment,
          page: pageParam,
          page_size: PAGE_SIZE,
        },
      });
      return data;
    },
    getNextPageParam: (lastPage, _allPages, lastPageParam) => {
      const total = lastPage.page_info?.total ?? 0;
      const loaded = (lastPageParam as number) * PAGE_SIZE;
      return loaded < total ? (lastPageParam as number) + 1 : undefined;
    },
    staleTime: 30_000,
  });

  // 扁平展平所有已加载的 pages
  const items = useMemo(
    () => (news.data?.pages ?? []).flatMap((p) => p.items ?? []),
    [news.data],
  );

  const total = news.data?.pages?.[0]?.page_info?.total ?? 0;

  // 触底加载：sentinel 进入滚动容器视口时 fetchNextPage
  // 把 useInfiniteQuery 暴露的方法 ref 化，规避"deps 含整个对象"的 lint 误报
  const fetchNextRef = useRef(news.fetchNextPage);
  const hasNextRef = useRef(news.hasNextPage);
  const fetchingRef = useRef(news.isFetchingNextPage);
  fetchNextRef.current = news.fetchNextPage;
  hasNextRef.current = news.hasNextPage;
  fetchingRef.current = news.isFetchingNextPage;

  useEffect(() => {
    const el = sentinelRef.current;
    const root = scrollRootRef.current;
    if (!el || !root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const e = entries[0];
        if (e.isIntersecting && hasNextRef.current && !fetchingRef.current) {
          fetchNextRef.current();
        }
      },
      { root, rootMargin: "120px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [items.length]);

  return (
    <Space direction="vertical" size={24} className="w-full">
      <PageHeader
        title="新闻列表"
        subtitle="标的关联新闻 + AI 情绪评分"
      />

      <Card size="small" className="w-full">
        <Space wrap size="middle">
          <Input.Search
            placeholder="标的代码"
            allowClear
            style={{ width: 200 }}
            onSearch={(v) => setFilters((f) => ({ ...f, symbol: v.trim() }))}
          />
          <Select
            value={filters.days}
            style={{ width: 140 }}
            onChange={(v) => setFilters((f) => ({ ...f, days: v }))}
            options={[
              { value: 1, label: "最近 1 天" },
              { value: 3, label: "最近 3 天" },
              { value: 7, label: "最近 7 天" },
              { value: 14, label: "最近 14 天" },
              { value: 30, label: "最近 30 天" },
            ]}
          />
          <Select
            value={filters.sentiment}
            placeholder="情绪"
            allowClear
            style={{ width: 140 }}
            onChange={(v) => setFilters((f) => ({ ...f, sentiment: v }))}
            options={[
              { value: "positive", label: "看多" },
              { value: "negative", label: "看空" },
              { value: "neutral", label: "中性" },
            ]}
          />
        </Space>
      </Card>

      {news.isLoading ? (
        <Skeleton active />
      ) : news.isError ? (
        <QueryErrorState error={news.error} onRetry={() => news.refetch()} />
      ) : items.length === 0 ? (
        <Card><Empty description="暂无新闻" /></Card>
      ) : (
        // 容器 max-height 限制为视口 60%，内部滚动；不再"页面一直往下长"
        // overscroll-behavior:contain 阻止滚轮事件冒泡到外层 AppLayout Content，
        // 解决"内层 + 外层双滚动容器冲突"——之前滚轮被外层先消费导致内层看似卡住。
        <div
          ref={scrollRootRef}
          className="w-full"
          style={{
            maxHeight: "60vh",
            overflowY: "auto",
            overscrollBehavior: "contain",
            paddingRight: 4,
          }}
        >
          <Space direction="vertical" className="w-full" size="middle">
            <Typography.Text type="secondary">
              共 {total} 条（已加载 {items.length}）
            </Typography.Text>
            {items.map((item, idx) => {
              const sentimentVariant =
                item.sentiment === "positive"
                  ? "success"
                  : item.sentiment === "negative"
                  ? "error"
                  : "neutral";
              const sentimentLabel = SENTIMENT_LABELS[item.sentiment ?? ""] ?? item.sentiment;
              return (
                <MotionCard key={item.id} delay={Math.min(idx * 0.02, 0.3)}>
                  <Card size="small" className="card-hoverable w-full">
                    <Space direction="vertical" size={6} className="w-full">
                      <Space wrap>
                        <Typography.Text strong style={{ fontSize: 15 }}>{item.title}</Typography.Text>
                        {item.sentiment && (
                          <StatusTag
                            value={sentimentLabel ?? ""}
                            variantMap={{ [sentimentLabel ?? ""]: sentimentVariant }}
                            labelMap={{
                              [sentimentLabel ?? ""]:
                                item.sentiment === "positive"
                                  ? "▲ 看多"
                                  : item.sentiment === "negative"
                                  ? "▼ 看空"
                                  : "— 中性",
                            }}
                          />
                        )}
                        <ScoredTag item={item} />
                      </Space>
                      <Space wrap size="small">
                        {item.source && <Tag bordered={false}>{item.source}</Tag>}
                        {item.published_at && (
                          <Typography.Text type="secondary" className="text-xs">
                            {dayjs(item.published_at).format("YYYY-MM-DD HH:mm")}
                          </Typography.Text>
                        )}
                      </Space>
                      {item.related_symbols && item.related_symbols.length > 0 && (
                        <Space wrap size={4}>
                          {item.related_symbols.map((s) => (
                            <span
                              key={s}
                              className="status-tag status-tag-info"
                              style={{ cursor: "pointer" }}
                              onClick={() => navigate(`/asset-detail/${s}`)}
                              role="button"
                              tabIndex={0}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  navigate(`/asset-detail/${s}`);
                                }
                              }}
                            >
                              {s}
                            </span>
                          ))}
                        </Space>
                      )}
                    </Space>
                  </Card>
                </MotionCard>
              );
            })}
            {/* 触底 sentinel + 加载状态提示 */}
            <div ref={sentinelRef} style={{ height: 1 }} />
            <div className="text-center py-2">
              {news.isFetchingNextPage ? (
                <Typography.Text type="secondary" className="text-xs">加载中…</Typography.Text>
              ) : news.hasNextPage ? (
                <Typography.Text type="secondary" className="text-xs">滚动以加载更多</Typography.Text>
              ) : (
                <Typography.Text type="secondary" className="text-xs">已加载全部 {items.length} 条</Typography.Text>
              )}
            </div>
          </Space>
        </div>
      )}
    </Space>
  );
}
