import { Layout, Typography, Space } from "antd";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { HealthIndicator } from "./HealthIndicator";

const { Sider, Header, Content } = Layout;

// 应用整体布局：左侧导航 + 顶部 API 状态 + 主内容区
export function AppLayout() {
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
            📊 MarketLens
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
            <Typography.Text type="secondary">后端</Typography.Text>
            <Typography.Text code>http://localhost:8000</Typography.Text>
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
