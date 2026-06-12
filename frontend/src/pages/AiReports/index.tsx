import { Card, Col, DatePicker, Empty, Progress, Row, Select, Skeleton, Space, Tooltip, Typography, message, Button } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import dayjs, { Dayjs } from "dayjs";
import { apiClient, extractErrorMessage } from "@/api/client";
import type { AIReport, GenerateReportsResponse, PageResult } from "@/api/types";
import { MotionCard } from "@/components/shared/MotionCard";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryErrorState } from "@/components/shared/QueryErrorState";
import { StatusTag } from "@/components/shared/StatusTag";

const ACTION_VARIANT_MAP: Record<string, "success" | "error" | "warning" | "info" | "neutral" | "accent"> = {
  buy: "success",
  sell: "error",
  watch: "info",
  avoid: "neutral",
};

const RISK_VARIANT_MAP: Record<string, "success" | "error" | "warning" | "info" | "neutral"> = {
  low: "success",
  medium: "warning",
  high: "error",
};

const ACTION_LABELS: Record<string, string> = {
  buy: "▲ 买入",
  sell: "▼ 卖出",
  watch: "○ 观望",
  avoid: "✕ 回避",
};

const RISK_LABELS: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
};

// 把 news_ai_scored_pct 渲染为彩色 Progress + 提示
function NewsAiScoredPct({ pct }: { pct: number | null | undefined }) {
  if (pct === null || pct === undefined) {
    return (
      <Tooltip title="本次证据包无新闻, 无法评估 AI 评分覆盖率">
        <StatusTag
          value="无新闻证据"
          variantMap={{ "无新闻证据": "neutral" }}
          labelMap={{ "无新闻证据": "○ 无新闻证据" }}
        />
      </Tooltip>
    );
  }
  const color =
    pct >= 80 ? "var(--color-success)" : pct >= 40 ? "var(--color-warning)" : "var(--color-error)";
  return (
    <Tooltip
      title={`近 7 天这只票的新闻中, ${pct.toFixed(0)}% 经过 DeepSeek 评分; 其余为 Provider 原值或迁移前数据`}
    >
      <Space size={6} className="w-full">
        <Typography.Text type="secondary" className="text-xs" style={{ minWidth: 96 }}>
          AI 评分覆盖
        </Typography.Text>
        <Progress
          percent={pct}
          size="small"
          strokeColor={color}
          showInfo
          format={(p) => `${p?.toFixed(0) ?? 0}%`}
          style={{ flex: 1, margin: 0 }}
        />
      </Space>
    </Tooltip>
  );
}

// 渲染 sector_exposure top 3 板块
function SectorExposureChips({ sectors }: { sectors: AIReport["sector_exposure"] }) {
  if (!sectors || sectors.length === 0) return null;
  return (
    <Space wrap size={4}>
      {sectors.slice(0, 3).map((s) => {
        const total = s.positive + s.negative + s.neutral;
        const variant =
          s.positive > s.negative && s.positive >= total * 0.5
            ? "success"
            : s.negative > s.positive && s.negative >= total * 0.5
            ? "error"
            : "neutral";
        const icon = variant === "success" ? "▲" : variant === "error" ? "▼" : "·";
        const tip = `${s.sector}: 共 ${s.count} 条, 正${s.positive}/负${s.negative}/中${s.neutral}, 平均置信 ${s.avg_confidence?.toFixed(2) ?? "-"}`;
        return (
          <Tooltip key={s.sector} title={tip}>
            <span className={`status-tag status-tag-${variant}`} style={{ fontSize: 11 }}>
              <span className="status-icon">{icon}</span>
              <span>{s.sector} · {s.count}</span>
            </span>
          </Tooltip>
        );
      })}
    </Space>
  );
}

interface ReportsFilter {
  date?: Dayjs;
  action?: string;
  risk_level?: string;
}

// AI 报告列表：日期 / 动作 / 风险 筛选 + 手动生成
export default function AiReportsPage() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<ReportsFilter>({});

  const reports = useQuery<PageResult<AIReport>>({
    queryKey: ["reports", filter],
    queryFn: async () => {
      const { data } = await apiClient.get<PageResult<AIReport>>("/reports", {
        params: {
          date: filter.date?.format("YYYY-MM-DD"),
          action: filter.action,
          risk_level: filter.risk_level,
          page: 1,
          page_size: 20,
        },
      });
      return data;
    },
  });

  const generate = useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<GenerateReportsResponse>(
        "/reports/generate",
        { force: false },
        { timeout: 180_000 },
      );
      return data;
    },
    onSuccess: (data) => {
      message.success(`生成 ${data.generated} 份，跳过 ${data.skipped} 份`);
      queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
    onError: (err) => {
      message.error(`生成失败：${extractErrorMessage(err)}`);
    },
  });

  return (
    <Space direction="vertical" size={24} className="w-full">
      <PageHeader
        title="AI 报告"
        subtitle="基于证据驱动的 AI 分析报告（规则引擎 + 实时数据）"
        extra={
          <Button
            type="primary"
            loading={generate.isPending}
            onClick={() => generate.mutate()}
          >
            🤖 手动生成报告
          </Button>
        }
      />

      <Card size="small" className="w-full">
        <Space wrap size="middle">
          <DatePicker
            placeholder="日期"
            value={filter.date ?? null}
            onChange={(v) => setFilter((f) => ({ ...f, date: v ?? undefined }))}
            allowClear
          />
          <Select
            placeholder="动作建议"
            allowClear
            style={{ width: 140 }}
            value={filter.action}
            onChange={(v) => setFilter((f) => ({ ...f, action: v }))}
            options={[
              { value: "buy", label: "买入" },
              { value: "sell", label: "卖出" },
              { value: "watch", label: "观望" },
              { value: "avoid", label: "回避" },
            ]}
          />
          <Select
            placeholder="风险等级"
            allowClear
            style={{ width: 140 }}
            value={filter.risk_level}
            onChange={(v) => setFilter((f) => ({ ...f, risk_level: v }))}
            options={[
              { value: "low", label: "低" },
              { value: "medium", label: "中" },
              { value: "high", label: "高" },
            ]}
          />
        </Space>
      </Card>

      {reports.isLoading ? (
        <Skeleton active />
      ) : reports.isError ? (
        <QueryErrorState error={reports.error} onRetry={reports.refetch} />
      ) : (reports.data?.items ?? []).length === 0 ? (
        <Card><Empty description="暂无报告" /></Card>
      ) : (
        <Row gutter={[16, 16]}>
          {reports.data!.items.map((r, idx) => (
            <Col key={r.id} xs={24} md={12} lg={8}>
              <MotionCard delay={Math.min(idx * 0.03, 0.3)}>
                <Card
                  size="small"
                  className="card-hoverable h-full"
                  title={
                    <Space>
                      <Typography.Text strong>{r.symbol}</Typography.Text>
                      <Typography.Text type="secondary">{r.name}</Typography.Text>
                    </Space>
                  }
                  extra={
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {dayjs(r.generated_at).format("MM-DD HH:mm")}
                    </Typography.Text>
                  }
                >
                  <Space direction="vertical" className="w-full" size={10}>
                    <Space size={6}>
                      <StatusTag
                        value={r.action}
                        variantMap={{ [r.action]: ACTION_VARIANT_MAP[r.action] ?? "neutral" }}
                        labelMap={{ [r.action]: ACTION_LABELS[r.action] ?? r.action }}
                      />
                      <StatusTag
                        value={r.risk_level}
                        variantMap={{ [r.risk_level]: RISK_VARIANT_MAP[r.risk_level] ?? "neutral" }}
                        labelMap={{ [r.risk_level]: RISK_LABELS[r.risk_level] ?? r.risk_level }}
                      />
                    </Space>
                    <Progress
                      percent={Math.round(r.confidence * 100)}
                      size="small"
                      showInfo
                      strokeColor="var(--color-primary)"
                    />
                    <NewsAiScoredPct pct={r.news_ai_scored_pct} />
                    {r.sector_exposure && r.sector_exposure.length > 0 && (
                      <SectorExposureChips sectors={r.sector_exposure} />
                    )}
                    <Typography.Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 2 }}>
                      {r.summary}
                    </Typography.Paragraph>
                    {r.bullish_reasons && r.bullish_reasons.length > 0 && (
                      <Typography.Text style={{ color: "var(--color-success)" }} className="text-xs">
                        ▲ {r.bullish_reasons[0]}
                      </Typography.Text>
                    )}
                    {r.bearish_reasons && r.bearish_reasons.length > 0 && (
                      <Typography.Text style={{ color: "var(--color-error)" }} className="text-xs">
                        ▼ {r.bearish_reasons[0]}
                      </Typography.Text>
                    )}
                  </Space>
                </Card>
              </MotionCard>
            </Col>
          ))}
        </Row>
      )}
    </Space>
  );
}
