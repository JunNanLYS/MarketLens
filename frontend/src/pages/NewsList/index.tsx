import { Card, Empty, Input, Select, Skeleton, Space, Tag, Tooltip, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
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

// 新闻列表：单只读端点 + 3 个筛选器（symbol / days / sentiment）
export default function NewsListPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<NewsFilters>({ symbol: "", days: 7 });

  const { data, isLoading, isError, error, refetch } = useQuery<PageResult<NewsItem>>({
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

      {isLoading ? (
        <Skeleton active />
      ) : isError ? (
        <QueryErrorState error={error} onRetry={() => refetch()} />
      ) : items.length === 0 ? (
        <Card><Empty description="暂无新闻" /></Card>
      ) : (
        <Space direction="vertical" className="w-full" size="middle">
          <Typography.Text type="secondary">共 {data?.page_info.total ?? 0} 条</Typography.Text>
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
        </Space>
      )}
    </Space>
  );
}
