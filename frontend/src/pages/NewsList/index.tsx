import { Card, Empty, Input, Select, Skeleton, Space, Tag, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import dayjs from "dayjs";
import { apiClient, extractErrorMessage } from "@/api/client";
import type { NewsItem, PageResult } from "@/api/types";
import { SENTIMENT_COLORS, SENTIMENT_LABELS } from "@/utils/constants";
import { MotionCard } from "@/components/shared/MotionCard";

interface NewsFilters {
  symbol: string;
  days: number;
  sentiment?: "positive" | "negative" | "neutral";
}

// 新闻列表：单只读端点 + 3 个筛选器（symbol / days / sentiment）
export default function NewsListPage() {
  const [filters, setFilters] = useState<NewsFilters>({ symbol: "", days: 7 });

  const { data, isLoading, isError, error } = useQuery<PageResult<NewsItem>>({
    queryKey: ["news", filters],
    queryFn: async () => {
      const { data } = await apiClient.get<PageResult<NewsItem>>("/news", {
        params: {
          symbol: filters.symbol || undefined,
          days: filters.days,
          sentiment: filters.sentiment,
          page: 1,
          page_size: 50,
        },
      });
      return data;
    },
    staleTime: 60_000,
  });

  const items = data?.items ?? [];

  return (
    <Space direction="vertical" size="large" className="w-full">
      <Typography.Title level={3}>新闻列表</Typography.Title>

      <Card size="small">
        <Space wrap>
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

      {isLoading ? (
        <Skeleton active />
      ) : isError ? (
        <Card>
          <Typography.Text type="danger">加载失败：{extractErrorMessage(error)}</Typography.Text>
        </Card>
      ) : items.length === 0 ? (
        <Empty description="暂无新闻" />
      ) : (
        <Space direction="vertical" className="w-full" size="small">
          <Typography.Text type="secondary">共 {data?.page_info.total ?? 0} 条</Typography.Text>
          {items.map((item, idx) => (
            <MotionCard key={item.id} delay={Math.min(idx * 0.02, 0.3)}>
              <Card size="small" hoverable>
                <Space direction="vertical" size={4} className="w-full">
                  <Space wrap>
                    <Typography.Text strong>{item.title}</Typography.Text>
                    {item.sentiment && (
                      <Tag color={SENTIMENT_COLORS[item.sentiment] ?? "default"}>
                        {SENTIMENT_LABELS[item.sentiment] ?? item.sentiment}
                      </Tag>
                    )}
                  </Space>
                  <Space wrap size="small">
                    {item.source && <Tag>{item.source}</Tag>}
                    {item.published_at && (
                      <Typography.Text type="secondary" className="text-xs">
                        {dayjs(item.published_at).format("YYYY-MM-DD HH:mm")}
                      </Typography.Text>
                    )}
                  </Space>
                  {item.related_symbols && item.related_symbols.length > 0 && (
                    <Space wrap size={4}>
                      {item.related_symbols.map((s) => (
                        <Tag key={s} color="blue">
                          {s}
                        </Tag>
                      ))}
                    </Space>
                  )}
                </Space>
              </Card>
            </MotionCard>
          ))}
        </Space>
      )}
    </Space>
  );
}
