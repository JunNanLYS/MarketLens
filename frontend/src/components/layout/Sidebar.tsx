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

// 7 项导航，对应原 Streamlit sidebar 顺序
const ITEMS = [
  { key: "/tracked-assets", label: "追踪标的", icon: <FundOutlined /> },
  { key: "/asset-detail", label: "标的详情", icon: <ProfileOutlined /> },
  { key: "/ai-reports", label: "AI 报告", icon: <RobotOutlined /> },
  { key: "/portfolio", label: "投资组合", icon: <WalletOutlined /> },
  { key: "/news", label: "新闻列表", icon: <ReadOutlined /> },
  { key: "/task-status", label: "任务状态", icon: <ScheduleOutlined /> },
  { key: "/settings", label: "系统配置", icon: <SettingOutlined /> },
];

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <Menu
      mode="inline"
      selectedKeys={[location.pathname]}
      style={{ height: "100%", borderRight: 0 }}
      items={ITEMS}
      onClick={({ key }) => navigate(key)}
    />
  );
}
