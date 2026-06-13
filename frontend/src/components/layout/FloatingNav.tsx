import {
  FundOutlined,
  ProfileOutlined,
  RobotOutlined,
  WalletOutlined,
  ReadOutlined,
  ScheduleOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { motion, useReducedMotion } from "framer-motion";
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
// 选中态用 framer-motion 的 layoutId 在新旧位置间做 FLIP 滑动，
// 蓝色胶囊会从旧 tab 平滑流到新 tab。
//
// 性能优化：原 spring 动画（stiffness 420 + damping 34 + mass 0.7）每次切 tab
// 持续运算 200~300ms，期间 tab 内容也在重渲染，导致切页 + 切胶囊叠加卡顿。
// 改为：胶囊仍保留 layoutId FLIP 形变动画但用极短 tween（140ms linear），
// 视觉差异不可察觉但 GPU 压力大幅下降；fallback reduceMotion 直接瞬切。
export function FloatingNav() {
  const location = useLocation();
  const navigate = useNavigate();
  const active = getSelectedKey(location.pathname);
  const reduceMotion = useReducedMotion();

  return (
    <nav aria-label="主导航" className="floating-nav">
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
            {isActive && (
              <motion.span
                layoutId="floating-nav-active-pill"
                className="floating-nav-active-bg"
                aria-hidden="true"
                transition={
                  reduceMotion
                    ? { duration: 0 }
                    : { duration: 0.14, ease: "linear" }
                }
              />
            )}
            <span className="floating-nav-icon">{item.icon}</span>
            <span className="floating-nav-label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
