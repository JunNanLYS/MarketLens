import { Layout, Space, Typography } from "antd";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { HealthIndicator } from "./HealthIndicator";
import { ThemeToggle } from "./ThemeToggle";
import { KpiBar } from "./KpiBar";
import { CommandPalette } from "@/components/shared/CommandPalette";

const { Sider, Header, Content } = Layout;

// 应用整体布局：左侧导航 + 顶部 KPI Bar + 主内容区。
//
// 高度策略：外/内 Layout 用 min-h-screen + h-screen 锁死为视口高度，
// Content 自己 overflow:auto 滚动。否则 Sider 会被内容撑高（每个
// 页面高度不同，侧边栏长度跟着变）。
export function AppLayout() {
  return (
    <Layout className="min-h-screen h-screen">
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
      <Layout className="min-h-screen h-screen" style={{ background: "var(--color-bg-layout)" }}>
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
        <Content style={{ padding: 24, overflow: "auto", background: "var(--color-bg-layout)" }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
