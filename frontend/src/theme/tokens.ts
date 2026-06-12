// antd 主题 token：与 DESIGN.md §3.1 + §3.4 完整对齐。
// 浅色/深色两套独立色板，共用字体/圆角/控件高度。

/** 浅色主题色板：皇家蓝 + 玫红，参考 Editorial Fashion 调性 */
export const LIGHT_TOKENS = {
  // 主色
  colorPrimary: "#1E40AF",
  colorPrimaryHover: "#1D4ED8",
  colorPrimaryActive: "#1E3A8A",
  colorPrimaryBg: "#DBEAFE",
  colorPrimaryBgHover: "#BFDBFE",
  colorPrimaryBorder: "#93C5FD",
  colorPrimaryText: "#1E40AF",
  colorPrimaryTextHover: "#1D4ED8",
  colorPrimaryTextActive: "#1E3A8A",

  // 强调色
  colorInfo: "#0369A1",
  colorInfoHover: "#0284C7",
  colorInfoBg: "#E0F2FE",
  colorInfoBorder: "#7DD3FC",
  colorInfoText: "#0369A1",

  // 链接
  colorLink: "#1E40AF",
  colorLinkHover: "#1D4ED8",
  colorLinkActive: "#1E3A8A",

  // 成功 / 警告 / 错误
  colorSuccess: "#059669",
  colorSuccessBg: "#D1FAE5",
  colorSuccessBorder: "#6EE7B7",
  colorSuccessText: "#059669",

  colorWarning: "#D97706",
  colorWarningBg: "#FEF3C7",
  colorWarningBorder: "#FCD34D",
  colorWarningText: "#D97706",

  colorError: "#DC2626",
  colorErrorHover: "#EF4444",
  colorErrorBg: "#FEE2E2",
  colorErrorBorder: "#FCA5A5",
  colorErrorText: "#DC2626",

  // 背景阶梯
  colorBgBase: "#FAFBFC",
  colorBgContainer: "#FFFFFF",
  colorBgElevated: "#FFFFFF",
  colorBgLayout: "#F4F6F9",
  colorBgSpotlight: "#DBEAFE",
  colorBgMask: "rgba(15, 23, 42, 0.45)",

  // 边框
  colorBorder: "#E2E8F0",
  colorBorderSecondary: "#F1F5F9",

  // 文字
  colorText: "#0F172A",
  colorTextSecondary: "#475569",
  colorTextTertiary: "#94A3B8",
  colorTextQuaternary: "#CBD5E1",
  colorTextHeading: "#0F172A",
  colorTextLabel: "#475569",
  colorTextDescription: "#64748B",
  colorTextPlaceholder: "#94A3B8",
  colorTextDisabled: "#CBD5E1",

  // 填充（hover/active 等场景）
  colorFill: "#F1F5F9",
  colorFillSecondary: "#F8FAFC",
  colorFillTertiary: "#F4F6F9",
  colorFillQuaternary: "#FAFBFC",
} as const;

/** 深色主题色板：冷峻模式，OLED-friendly */
export const DARK_TOKENS = {
  // 主色
  colorPrimary: "#3B82F6",
  colorPrimaryHover: "#60A5FA",
  colorPrimaryActive: "#2563EB",
  colorPrimaryBg: "#172554",
  colorPrimaryBgHover: "#1E3A8A",
  colorPrimaryBorder: "#1D4ED8",
  colorPrimaryText: "#60A5FA",
  colorPrimaryTextHover: "#93C5FD",
  colorPrimaryTextActive: "#BFDBFE",

  // 信息
  colorInfo: "#38BDF8",
  colorInfoHover: "#7DD3FC",
  colorInfoBg: "#082F49",
  colorInfoBorder: "#0369A1",
  colorInfoText: "#7DD3FC",

  // 链接
  colorLink: "#60A5FA",
  colorLinkHover: "#93C5FD",
  colorLinkActive: "#3B82F6",

  // 成功 / 警告 / 错误
  colorSuccess: "#10B981",
  colorSuccessBg: "#022C22",
  colorSuccessBorder: "#065F46",
  colorSuccessText: "#34D399",

  colorWarning: "#F59E0B",
  colorWarningBg: "#451A03",
  colorWarningBorder: "#92400E",
  colorWarningText: "#FBBF24",

  colorError: "#EF4444",
  colorErrorHover: "#F87171",
  colorErrorBg: "#450A0A",
  colorErrorBorder: "#991B1B",
  colorErrorText: "#F87171",

  // 背景阶梯（OLED 冷峻模式）
  colorBgBase: "#0A0E14",
  colorBgContainer: "#141A24",
  colorBgElevated: "#1A2230",
  colorBgLayout: "#0E1218",
  colorBgSpotlight: "#172554",
  colorBgMask: "rgba(0, 0, 0, 0.65)",

  // 边框
  colorBorder: "#1E2A3B",
  colorBorderSecondary: "#172033",

  // 文字（避免纯白刺眼）
  colorText: "#E2E8F0",
  colorTextSecondary: "#94A3B8",
  colorTextTertiary: "#64748B",
  colorTextQuaternary: "#475569",
  colorTextHeading: "#F1F5F9",
  colorTextLabel: "#CBD5E1",
  colorTextDescription: "#94A3B8",
  colorTextPlaceholder: "#64748B",
  colorTextDisabled: "#475569",

  // 填充
  colorFill: "#1A2230",
  colorFillSecondary: "#172033",
  colorFillTertiary: "#141A24",
  colorFillQuaternary: "#0E1218",
} as const;

/** 跨主题共享 token：字体、圆角、控件高度 */
export const SHARED_TOKENS = {
  // 圆角（DESIGN.md §3.4）
  borderRadius: 8,
  borderRadiusLG: 12,
  borderRadiusSM: 6,
  borderRadiusXS: 4,

  // 控件
  controlHeight: 36,
  controlHeightLG: 44,
  controlHeightSM: 28,

  // 字体（DESIGN.md §3.2 — Inter 优先，系统字 fallback）
  fontFamily:
    'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Roboto Mono", "Menlo", monospace',
  fontFamilyCode:
    '"JetBrains Mono", "Roboto Mono", "SF Mono", Menlo, Consolas, monospace',

  // 字号
  fontSize: 14,
  fontSizeLG: 16,
  fontSizeSM: 12,

  // 字重
  fontWeightStrong: 600,

  // 行高
  lineHeight: 1.57,
  lineHeightLG: 1.5,
} as const;
