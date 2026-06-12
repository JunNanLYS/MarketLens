import { useEffect, useState } from "react";
import { Layout, Space, Typography } from "antd";
import { Outlet } from "react-router-dom";
import { HealthIndicator } from "./HealthIndicator";
import { ThemeToggle } from "./ThemeToggle";
import { KpiBar } from "./KpiBar";
import { FloatingNav } from "./FloatingNav";
import { CommandPalette } from "@/components/shared/CommandPalette";

const { Header, Content } = Layout;

// MarketLens 品牌 logo：SVG 折线图（DESIGN.md §1 品牌定位）
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

// 应用整体布局：
//   - 顶部 Header：左 logo + 中 FloatingNav 居中悬浮 + 右 KpiBar/操作
//   - Content：承载各 page
// 高度策略：Layout 用 min-h-screen + h-screen 锁死为视口高度，
// Content 自己 overflow:auto 滚动。
export function AppLayout() {
  // 命令面板开关状态：提升到 AppLayout，方便 Header 右侧的 ⌘K 按钮触发
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
    <Layout className="min-h-screen h-screen" style={{ background: "var(--color-bg-layout)" }}>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <Header
        style={{
          borderBottom: "1px solid var(--color-border)",
          paddingInline: 24,
          paddingBlock: 0,
          display: "grid",
          gridTemplateColumns: "1fr auto 1fr",
          alignItems: "center",
          background: "var(--color-bg-container)",
          height: 64,
          lineHeight: "64px",
          gap: 16,
          position: "sticky",
          top: 0,
          zIndex: 50,
        }}
      >
        {/* 左：品牌 logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
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

        {/* 中：悬浮胶囊导航（玻璃质感） */}
        <FloatingNav />

        {/* 右：KPI + 操作 */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 12, minWidth: 0 }}>
          <KpiBar />
          <Space size={12}>
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              title="按 ⌘K / Ctrl+K 搜索"
              aria-label="打开命令面板"
              className="floating-nav-item"
              style={{
                background: "var(--color-bg-base)",
                border: "1px solid var(--color-border)",
                color: "var(--color-text-secondary)",
                padding: "6px 12px",
                fontSize: 12,
                borderRadius: 10,
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontFamily: "inherit",
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
                }}
              >
                ⌘K
              </kbd>
              搜索
            </button>
            <HealthIndicator />
            <ThemeToggle />
          </Space>
        </div>
      </Header>
      <Content
        style={{
          padding: "32px 32px",
          overflow: "auto",
          background: "var(--color-bg-layout)",
        }}
      >
        <Outlet />
      </Content>
    </Layout>
  );
}
