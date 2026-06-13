import type { ReactNode } from "react";
import { MoonOutlined, SunOutlined } from "@ant-design/icons";
import { Segmented } from "antd";
import { usePreferencesStore, type ThemeMode } from "@/store/preferences";

const OPTIONS: { label: ReactNode; value: ThemeMode }[] = [
  { label: <SunOutlined />, value: "light" },
  { label: "系统", value: "system" },
  { label: <MoonOutlined />, value: "dark" },
];

/** 主题切换：浅色 / 系统 / 深色，三段式 Segmented */
export function ThemeToggle() {
  const theme = usePreferencesStore((s) => s.theme);
  const setTheme = usePreferencesStore((s) => s.setTheme);

  return (
    <Segmented
      size="small"
      value={theme}
      options={OPTIONS}
      onChange={(v) => setTheme(v as ThemeMode)}
    />
  );
}