import { Card, Empty, Input, Select, Skeleton, Space, Tag, Tooltip, Typography } from "antd";
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

// 渲染 "AI 已评分" 角标 + 置信度。ai_scored=false 时（迁移前数据 / 本次分析失败）
// 用灰色 tag 标 "未评分"，让用户对每条新闻的评分可信度心里有数。
function ScoredTag({ item }: { item: NewsItem }) {
  if (item.ai_scored) {
    const conf = typeof item.confidence === "number" ? item.confidence : null;
    const label = conf !== null ? `AI 评分 · ${conf.toFixed(2)}` : "AI 已评分";
    const reasonTip = item.sentiment_reason || "无理由";
    return (
      <Tooltip title={reasonTip}>
        <Tag color="geekblue" data-testid="ai-scored-tag">
          {label}
        </Tag>
      </Tooltip>
    );
  }
  return (
    <Tooltip title="该新闻采集时 DeepSeek 未出分（迁移前数据或本次分析失败），sentiment 字段取自原始数据源">
      <Tag color="default" data-testid="ai-unscored-tag">
        未评分
      </Tag>
    </Tooltip>
  );
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
                    <ScoredTag item={item} />
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
