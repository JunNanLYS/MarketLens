import { Card, Col, DatePicker, Empty, Progress, Row, Select, Skeleton, Space, Tag, Tooltip, Typography, message, Button } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import dayjs, { Dayjs } from "dayjs";
import { apiClient, extractErrorMessage } from "@/api/client";
import type { AIReport, GenerateReportsResponse, PageResult } from "@/api/types";
import { MotionCard } from "@/components/shared/MotionCard";

const ACTION_COLORS: Record<string, string> = {
  buy: "green",
  sell: "red",
  watch: "gold",
  avoid: "default",
};

const RISK_COLORS: Record<string, string> = {
  low: "green",
  medium: "gold",
  high: "red",
};

// 把 news_ai_scored_pct 渲染为彩色 Progress + 提示
// 100 = 全部 AI 评过分; 0 = 全是迁移前数据; null = 无新闻证据
function NewsAiScoredPct({ pct }: { pct: number | null | undefined }) {
  if (pct === null || pct === undefined) {
    return (
      <Tooltip title="本次证据包无新闻, 无法评估 AI 评分覆盖率">
        <Tag data-testid="ai-scored-pct-empty">无新闻证据</Tag>
      </Tooltip>
    );
  }
  const color = pct >= 80 ? "green" : pct >= 40 ? "gold" : "red";
  return (
    <Tooltip
      title={`近 7 天这只票的新闻中, ${pct.toFixed(0)}% 经过 DeepSeek 评分; 其余为 Provider 原值或迁移前数据`}
    >
      <Space size={4} className="w-full">
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

// 渲染 sector_exposure top 3 板块, 用颜色编码方向
function SectorExposureChips({ sectors }: { sectors: AIReport["sector_exposure"] }) {
  if (!sectors || sectors.length === 0) return null;
  return (
    <Space wrap size={4}>
      {sectors.slice(0, 3).map((s) => {
        const total = s.positive + s.negative + s.neutral;
        const color =
          s.positive > s.negative && s.positive >= total * 0.5
            ? "green"
            : s.negative > s.positive && s.negative >= total * 0.5
            ? "red"
            : "default";
        const tip = `${s.sector}: 共 ${s.count} 条, 正${s.positive}/负${s.negative}/中${s.neutral}, 平均置信 ${s.avg_confidence?.toFixed(2) ?? "-"}`;
        return (
          <Tooltip key={s.sector} title={tip}>
            <Tag color={color} data-testid="sector-exposure-tag">
              {s.sector} · {s.count}
            </Tag>
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
      const { data } = await apiClient.post<GenerateReportsResponse>("/reports/generate", {
        force: false,
      });
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
    <Space direction="vertical" size="large" className="w-full">
      <Typography.Title level={3}>AI 报告</Typography.Title>

      <Card size="small">
        <Space wrap>
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
          <Button type="primary" loading={generate.isPending} onClick={() => generate.mutate()}>
            手动生成报告
          </Button>
        </Space>
      </Card>

      {reports.isLoading ? (
        <Skeleton active />
      ) : reports.isError ? (
        <Card>
          <Typography.Text type="danger">加载失败：{extractErrorMessage(reports.error)}</Typography.Text>
        </Card>
      ) : (reports.data?.items ?? []).length === 0 ? (
        <Empty description="暂无报告" />
      ) : (
        <Row gutter={[16, 16]}>
          {reports.data!.items.map((r, idx) => (
            <Col key={r.id} xs={24} md={12} lg={8}>
              <MotionCard delay={Math.min(idx * 0.03, 0.3)}>
                <Card
                  size="small"
                  title={
                    <Space>
                      <Typography.Text strong>{r.symbol}</Typography.Text>
                      <Typography.Text type="secondary">{r.name}</Typography.Text>
                    </Space>
                  }
                  extra={dayjs(r.generated_at).format("MM-DD HH:mm")}
                >
                  <Space direction="vertical" className="w-full" size={8}>
                    <Space>
                      <Tag color={ACTION_COLORS[r.action] ?? "default"}>{r.action}</Tag>
                      <Tag color={RISK_COLORS[r.risk_level] ?? "default"}>{r.risk_level}</Tag>
                    </Space>
                    <Progress percent={Math.round(r.confidence * 100)} size="small" showInfo />
                    <NewsAiScoredPct pct={r.news_ai_scored_pct} />
                    {r.sector_exposure && r.sector_exposure.length > 0 && (
                      <SectorExposureChips sectors={r.sector_exposure} />
                    )}
                    <Typography.Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 2 }}>
                      {r.summary}
                    </Typography.Paragraph>
                    {r.bullish_reasons && r.bullish_reasons.length > 0 && (
                      <Typography.Text type="secondary" className="text-xs">
                        ▲ {r.bullish_reasons[0]}
                      </Typography.Text>
                    )}
                    {r.bearish_reasons && r.bearish_reasons.length > 0 && (
                      <Typography.Text type="secondary" className="text-xs">
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
