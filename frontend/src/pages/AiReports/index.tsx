import { Card, Col, DatePicker, Empty, Progress, Row, Select, Skeleton, Space, Tag, Typography, message, Button } from "antd";
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
