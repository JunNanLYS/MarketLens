import { Layout, Space, Typography } from "antd";
import { Outlet } from "react-router-dom";
import { getApiBaseUrlLabel } from "@/api/client";
import { Sidebar } from "./Sidebar";
import { HealthIndicator } from "./HealthIndicator";

const { Sider, Header, Content } = Layout;

// 应用整体布局：左侧导航 + 顶部接口状态 + 主内容区。
export function AppLayout() {
  const apiBaseUrlLabel = getApiBaseUrlLabel();

  return (
    <Layout className="h-full">
      <Sider
        width={220}
        theme="light"
        breakpoint="lg"
        collapsedWidth={64}
        style={{ borderRight: "1px solid #f0f0f0" }}
      >
        <div className="px-4 py-4">
          <Typography.Title level={4} style={{ margin: 0 }}>
            <span aria-hidden="true">📊 </span>
            <span>MarketLens</span>
          </Typography.Title>
        </div>
        <Sidebar />
      </Sider>
      <Layout>
        <Header
          style={{
            background: "#fff",
            borderBottom: "1px solid #f0f0f0",
            paddingInline: 16,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <Space>
            <Typography.Text type="secondary">接口地址</Typography.Text>
            <Typography.Text code>{apiBaseUrlLabel}</Typography.Text>
          </Space>
          <HealthIndicator />
        </Header>
        <Content style={{ padding: 24, overflow: "auto" }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
