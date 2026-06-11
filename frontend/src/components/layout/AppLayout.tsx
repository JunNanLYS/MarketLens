import { Layout, Space, Typography } from "antd";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { HealthIndicator } from "./HealthIndicator";
import { ThemeToggle } from "./ThemeToggle";
import { KpiBar } from "./KpiBar";
import { CommandPalette } from "@/components/shared/CommandPalette";

const { Sider, Header, Content } = Layout;

// 应用整体布局：左侧导航 + 顶部 KPI Bar + 主内容区。
export function AppLayout() {
  return (
    <Layout className="h-full">
      <CommandPalette />
      <Sider
        width={220}
        breakpoint="lg"
        collapsedWidth={64}
        style={{ borderRight: "1px solid var(--color-border-secondary)" }}
      >
        <div className="px-4 py-4">
          <Typography.Title level={4} style={{ margin: 0 }}>
            <span aria-hidden="true">📊 </span>
            <span>MarketLens</span>
          </Typography.Title>
        </div>
        <Sidebar />
      </Sider>
      <Layout className="h-full" style={{ background: "var(--color-bg-layout)" }}>
        <Header
          style={{
            borderBottom: "1px solid var(--color-border-secondary)",
            paddingInline: 16,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "var(--color-bg-container)",
          }}
        >
          <KpiBar />
          <Space>
            <HealthIndicator />
            <ThemeToggle />
          </Space>
        </Header>
        <Content className="h-full" style={{ padding: 24, overflow: "auto", background: "var(--color-bg-layout)" }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}