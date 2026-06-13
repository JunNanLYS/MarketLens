import { useEffect, useState } from "react";
import { Layout, Space, Typography } from "antd";
import { Outlet, useLocation } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { HealthIndicator } from "./HealthIndicator";
import { ThemeToggle } from "./ThemeToggle";
import { KpiBar } from "./KpiBar";
import { FloatingNav } from "./FloatingNav";
import { CommandPalette } from "@/components/shared/CommandPalette";

const { Content } = Layout;

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
  const location = useLocation();
  const reduceMotion = useReducedMotion();

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
      <header
        className="app-header-glass"
        style={{
          paddingInline: 20,
          display: "grid",
          gridTemplateColumns: "1fr auto 1fr",
          alignItems: "center",
          height: 52,
          gap: 12,
        }}
      >
        {/* 左：品牌 logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
          <MarketLensLogo size={20} />
          <Typography.Title
            level={5}
            style={{
              margin: 0,
              fontSize: 15,
              fontWeight: 700,
              letterSpacing: "-0.02em",
              color: "var(--color-text-primary)",
              whiteSpace: "nowrap",
            }}
          >
            MarketLens
          </Typography.Title>
        </div>

        {/* 中：悬浮胶囊导航（玻璃质感） */}
        <FloatingNav />

        {/* 右：搜索 + 健康指示 + 主题切换 */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, minWidth: 0 }}>
          <Space size={10}>
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              title="按 ⌘K / Ctrl+K 搜索"
              aria-label="打开命令面板"
              className="app-search-pill"
            >
              <kbd>⌘K</kbd>
              搜索
            </button>
            <HealthIndicator />
            <ThemeToggle />
          </Space>
        </div>
      </header>
      <Content
        style={{
          padding: "72px 32px 32px",
          // 保持 overflow:auto 让长页面整体可滚动。
          // NewsList 等"内部滑动视窗"组件用 overscroll-behavior:contain
          // 阻止滚轮事件冒泡到外层，避免双滚动冲突。
          overflow: "auto",
          background: "var(--color-bg-layout)",
        }}
      >
        {/* 二级 KPI 条：贴在 Header 下方，作为每页通用顶栏 */}
        <div style={{ marginBottom: 24 }}>
          <KpiBar />
        </div>
        {/* 路由切换：AnimatePresence 用 wait 模式避免新旧页面同时占布局空间。 */}
        <AnimatePresence initial={false} mode="wait">
          <motion.div
            key={location.pathname}
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={reduceMotion ? undefined : { opacity: 0 }}
            transition={{ duration: 0.12, ease: "linear" }}
            style={{ willChange: "opacity" }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </Content>
    </Layout>
  );
}
