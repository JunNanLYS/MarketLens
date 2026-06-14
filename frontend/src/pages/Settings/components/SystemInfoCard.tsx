import { Card, Col, Collapse, Descriptions, Divider, Row, Space, Typography } from "antd";

// 系统信息卡 + 设计系统预览（Color Tokens / Status Tags / Typography Scale）。
// 全部为纯静态展示，不持有任何状态或 mutation。
export function SystemInfoCard() {
  return (
    <Space direction="vertical" size={24} className="w-full">
      <Card title="系统信息" size="small" className="w-full">
        <Row gutter={16}>
          <Col span={8}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="数据库">SQLite（本地文件）</Descriptions.Item>
              <Descriptions.Item label="数据存储">全部本地，不上传云端</Descriptions.Item>
              <Descriptions.Item label="AI 引擎">规则引擎 + 证据驱动</Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>
      </Card>

      <Collapse
        ghost
        items={[
          {
            key: "design-system",
            label: (
              <Typography.Text type="secondary">🎨 设计系统预览</Typography.Text>
            ),
            children: (
              <Card size="small">
                <Space direction="vertical" size="middle" className="w-full">
                  <div>
                    <Typography.Text strong>Color Tokens</Typography.Text>
                    <div className="grid grid-cols-8 gap-2 mt-2">
                      {[
                        { name: "primary", token: "var(--color-primary)" },
                        { name: "primary-soft", token: "var(--color-primary-soft)" },
                        { name: "accent", token: "var(--color-accent)" },
                        { name: "accent-soft", token: "var(--color-accent-soft)" },
                        { name: "success", token: "var(--color-success)" },
                        { name: "warning", token: "var(--color-warning)" },
                        { name: "error", token: "var(--color-error)" },
                        { name: "info", token: "var(--color-info)" },
                      ].map((c) => (
                        <div key={c.name} className="text-center">
                          <div
                            style={{
                              background: c.token,
                              width: "100%",
                              height: 36,
                              borderRadius: 6,
                              border: "1px solid var(--color-border)",
                            }}
                          />
                          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                            {c.name}
                          </Typography.Text>
                        </div>
                      ))}
                    </div>
                  </div>
                  <Divider style={{ margin: 0 }} />
                  <div>
                    <Typography.Text strong>Status Tags</Typography.Text>
                    <div className="flex gap-2 mt-2 flex-wrap">
                      {[
                        { variant: "success" as const, label: "成功", icon: "✓" },
                        { variant: "error" as const, label: "失败", icon: "✕" },
                        { variant: "warning" as const, label: "警告", icon: "!" },
                        { variant: "info" as const, label: "运行中", icon: "i" },
                        { variant: "neutral" as const, label: "已跳过", icon: "·" },
                        { variant: "accent" as const, label: "重要", icon: "★" },
                      ].map((t) => (
                        <span key={t.variant} className={`status-tag status-tag-${t.variant}`}>
                          <span className="status-icon">{t.icon}</span>
                          <span>{t.label}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                  <Divider style={{ margin: 0 }} />
                  <div>
                    <Typography.Text strong>Typography Scale</Typography.Text>
                    <div className="mt-2 space-y-1">
                      <div style={{ fontSize: 32, lineHeight: "40px", fontWeight: 700 }}>Display 32/40</div>
                      <div style={{ fontSize: 24, lineHeight: "32px", fontWeight: 700 }}>H1 24/32</div>
                      <div style={{ fontSize: 20, lineHeight: "28px", fontWeight: 600 }}>H2 20/28</div>
                      <div style={{ fontSize: 16, lineHeight: "24px", fontWeight: 600 }}>H3 16/24</div>
                      <div style={{ fontSize: 14, lineHeight: "22px" }}>Body 14/22 正文</div>
                      <div style={{ fontSize: 12, lineHeight: "18px", color: "var(--color-text-secondary)" }}>Caption 12/18 辅助</div>
                      <div className="kpi-chip-value">Metric 28/36 数字</div>
                    </div>
                  </div>
                </Space>
              </Card>
            ),
          },
        ]}
      />
    </Space>
  );
}
