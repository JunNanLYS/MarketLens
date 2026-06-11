// antd 主题 token：品牌色 + 语义色 + 布局参数，浅色/深色共享。

/** 浅色主题色板 */
export const LIGHT_TOKENS = {
  colorPrimary: "#0F2D5C",
  colorSuccess: "#16A34A",
  colorWarning: "#D97706",
  colorError: "#DC2626",
  colorInfo: "#2563EB",

  colorBgBase: "#FFFFFF",
  colorBgContainer: "#FFFFFF",
  colorBgElevated: "#FFFFFF",
  colorBgLayout: "#F5F5F5",
  colorBorder: "#D9D9D9",
  colorBorderSecondary: "#F0F0F0",

  colorText: "#141414",
  colorTextSecondary: "#666666",
  colorTextTertiary: "#999999",
  colorTextQuaternary: "#CCCCCC",

  borderRadius: 8,
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Roboto Mono", "Menlo", monospace',
  controlHeight: 36,
} as const;

/** 深色主题覆盖（仅色板，其余继承 LIGHT_TOKENS） */
export const DARK_TOKENS = {
  colorPrimary: "#3B82F6",
  colorSuccess: "#34D399",
  colorWarning: "#FBBF24",
  colorError: "#F87171",
  colorInfo: "#60A5FA",

  colorBgBase: "#141414",
  colorBgContainer: "#1F1F1F",
  colorBgElevated: "#262626",
  colorBgLayout: "#0A0A0A",
  colorBorder: "#424242",
  colorBorderSecondary: "#303030",

  colorText: "#E5E5E5",
  colorTextSecondary: "#A3A3A3",
  colorTextTertiary: "#737373",
  colorTextQuaternary: "#525252",
} as const;

/** 语义 token（通用，浅色深色共用） */
export const SHARED_TOKENS = {
  borderRadius: 8,
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Roboto Mono", "Menlo", monospace',
  controlHeight: 36,
} as const;