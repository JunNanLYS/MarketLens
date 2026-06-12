import { useEffect, useState } from "react";
import { Layout, Space, Tag, Typography } from "antd";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { HealthIndicator } from "./HealthIndicator";
import { ThemeToggle } from "./ThemeToggle";
import { KpiBar } from "./KpiBar";
import { CommandPalette } from "@/components/shared/CommandPalette";

const { Sider, Header, Content } = Layout;

// MarketLens 品牌 logo：SVG 折线图 icon（DESIGN.md §1 品牌定位）
function MarketLensLogo({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      style={{ flexShrink: 0 }}
    >
      <path
        d="M3 17l5-5 4 3 5-7 4 5"
        stroke="var(--color-primary)"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="8" cy="12" r="1.6" fill="var(--color-primary)" />
      <circle cx="12" cy="15" r="1.6" fill="var(--color-primary)" />
      <circle cx="17" cy="8" r="1.6" fill="var(--color-accent)" />
      <circle cx="21" cy="13" r="1.6" fill="var(--color-primary)" />
    </svg>
  );
}

// 应用整体布局：左侧导航 + 顶部 KPI Bar + 主内容区。
//
// 高度策略：外/内 Layout 用 min-h-screen + h-screen 锁死为视口高度，
// Content 自己 overflow:auto 滚动。否则 Sider 会被内容撑高（每个
// 页面高度不同，侧边栏长度跟着变）。
export function AppLayout() {
  // 命令面板开关状态：提升到 AppLayout，方便 Header 里的 ⌘K 提示 Tag 点击触发
  const [paletteOpen, setPaletteOpen] = useState(false);

  // ⌘K / Ctrl+K 全局快捷键统一在 AppLayout 监听；CommandPalette 内部不再重复绑定
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <Layout className="min-h-screen h-screen">
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <Sider
        width={220}
        breakpoint="lg"
        collapsedWidth={64}
        style={{
          borderRight: "1px solid var(--color-border)",
          background: "var(--color-bg-container)",
        }}
      >
        <div
          style={{
            padding: "16px 20px",
            display: "flex",
            alignItems: "center",
            gap: 10,
            borderBottom: "1px solid var(--color-border)",
            height: 56,
          }}
        >
          <MarketLensLogo size={22} />
          <Typography.Title
            level={5}
            style={{
              margin: 0,
              fontSize: 16,
              fontWeight: 700,
              letterSpacing: "-0.02em",
              color: "var(--color-text-primary)",
            }}
          >
            MarketLens
          </Typography.Title>
        </div>
        <Sidebar />
      </Sider>
      <Layout className="min-h-screen h-screen" style={{ background: "var(--color-bg-layout)" }}>
        <Header
          style={{
            borderBottom: "1px solid var(--color-border)",
            paddingInline: 24,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "var(--color-bg-container)",
            height: 56,
            lineHeight: "56px",
          }}
        >
          <KpiBar />
          <Space size={12}>
            <Tag
              style={{
                cursor: "pointer",
                userSelect: "none",
                background: "var(--color-bg-base)",
                borderColor: "var(--color-border)",
                color: "var(--color-text-secondary)",
                padding: "2px 10px",
                borderRadius: 6,
                fontSize: 12,
              }}
              onClick={() => setPaletteOpen(true)}
              title="按 ⌘K / Ctrl+K 搜索"
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setPaletteOpen(true);
                }
              }}
            >
              <kbd
                style={{
                  fontFamily: "inherit",
                  fontSize: 11,
                  padding: "1px 5px",
                  background: "var(--color-bg-container)",
                  border: "1px solid var(--color-border)",
                  borderRadius: 3,
                  marginRight: 6,
                }}
              >
                ⌘K
              </kbd>
              搜索
            </Tag>
            <HealthIndicator />
            <ThemeToggle />
          </Space>
        </Header>
        <Content
          style={{
            padding: "24px 32px",
            overflow: "auto",
            background: "var(--color-bg-layout)",
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
