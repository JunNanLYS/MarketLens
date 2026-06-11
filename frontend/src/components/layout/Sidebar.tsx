import { Menu } from "antd";
import {
  FundOutlined,
  ProfileOutlined,
  RobotOutlined,
  WalletOutlined,
  ReadOutlined,
  ScheduleOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { useLocation, useNavigate } from "react-router-dom";

// 7 项导航，对应原 Streamlit sidebar 顺序。
const ITEMS = [
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

function getSelectedMenuKey(pathname: string): string | null {
  const matchedItem = [...ITEMS]
    .sort((left, right) => right.key.length - left.key.length)
    .find((item) => matchesRoute(pathname, item.key));

  return matchedItem?.key ?? null;
}

// 折叠态下 antd Menu 不会自动撑满 Sider 高度，菜单项会堆在顶部
// 导致下半部分空白。包一层 flex 容器，强制让菜单区域填满。
// ul 内的菜单项分布由 global.css 中的 .ant-layout-sider .ant-menu-root 规则接管。
export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const selectedKey = getSelectedMenuKey(location.pathname);

  return (
    <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
      <Menu
        mode="inline"
        selectedKeys={selectedKey ? [selectedKey] : []}
        style={{ flex: 1, borderRight: 0, minHeight: 0 }}
        items={ITEMS}
        onClick={({ key }) => navigate(key)}
      />
    </div>
  );
}
