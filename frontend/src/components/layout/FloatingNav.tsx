import {
  FundOutlined,
  ProfileOutlined,
  RobotOutlined,
  WalletOutlined,
  ReadOutlined,
  ScheduleOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import type { ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";

// 7 项导航 — 对应原 Streamlit sidebar 顺序。
const ITEMS: Array<{
  key: string;
  label: string;
  icon: ReactNode;
}> = [
  { key: "/tracked-assets", label: "追踪标的", icon: <FundOutlined /> },
  { key: "/asset-detail", label: "标的详情", icon: <ProfileOutlined /> },
  { key: "/ai-reports", label: "AI 报告", icon: <RobotOutlined /> },
  { key: "/portfolio", label: "投资组合", icon: <WalletOutlined /> },
  { key: "/news", label: "新闻列表", icon: <ReadOutlined /> },
  { key: "/task-status", label: "任务状态", icon: <ScheduleOutlined /> },
  { key: "/settings", label: "系统配置", icon: <SettingOutlined /> },
];

function matchesRoute(pathname: string, routeKey: string): boolean {
  return pathname === routeKey || pathname.startsWith(`${routeKey}/`);
}

function getSelectedKey(pathname: string): string {
  const matched = [...ITEMS]
    .sort((left, right) => right.key.length - left.key.length)
    .find((item) => matchesRoute(pathname, item.key));
  return matched?.key ?? "/tracked-assets";
}

// 顶部悬浮胶囊导航：macOS / VisionOS 玻璃质感。
// - 居中悬浮在 Content 顶部，pointer-events:auto 不挡点击
// - 玻璃 backdrop-filter blur(20px) saturate(180%)
// - 选中态：胶囊高亮 + 微缩放 + 阴影抬升
// - 圆角胶囊：未选中 10px / 选中 14px（pill 形状）
export function FloatingNav() {
  const location = useLocation();
  const navigate = useNavigate();
  const active = getSelectedKey(location.pathname);

  return (
    <nav
      aria-label="主导航"
      className="floating-nav"
    >
      {ITEMS.map((item) => {
        const isActive = item.key === active;
        return (
          <button
            key={item.key}
            type="button"
            onClick={() => navigate(item.key)}
            aria-current={isActive ? "page" : undefined}
            className={`floating-nav-item ${isActive ? "floating-nav-item-active" : ""}`}
            title={item.label}
          >
            <span className="floating-nav-icon">{item.icon}</span>
            <span className="floating-nav-label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
