import type { ReactNode } from "react";
import { MoonOutlined, SunOutlined } from "@ant-design/icons";
import { Button, Segmented } from "antd";
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

/** 移动端 / 紧凑场景的图标按钮切换（light ↔ dark） */
export function ThemeToggleCompact() {
  const theme = usePreferencesStore((s) => s.theme);
  const setTheme = usePreferencesStore((s) => s.setTheme);
  const resolved =
    theme === "system"
      ? typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : theme;

  return (
    <Button
      type="text"
      icon={resolved === "dark" ? <SunOutlined /> : <MoonOutlined />}
      onClick={() => setTheme(resolved === "dark" ? "light" : "dark")}
      aria-label={resolved === "dark" ? "切换到浅色模式" : "切换到深色模式"}
    />
  );
}