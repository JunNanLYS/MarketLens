import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, App as AntdApp, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import "antd/dist/reset.css";
import "@/styles/global.css";
import { App } from "@/App";
import { usePreferencesStore } from "@/store/preferences";
import { LIGHT_TOKENS, DARK_TOKENS, SHARED_TOKENS } from "@/theme/tokens";
import { useEffect, useState } from "react";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function ThemedApp() {
  const mode = usePreferencesStore((s) => s.theme);
  const [systemDark, setSystemDark] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches,
  );

  // 监听系统偏好变化
  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  // 解析实际主题
  const resolvedTheme = mode === "system" ? (systemDark ? "dark" : "light") : mode;

  // 同步 html data-theme 属性，供 CSS 变量 + echarts 读取
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", resolvedTheme);
    // 同步 meta theme-color
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute("content", resolvedTheme === "dark" ? "#141414" : "#FFFFFF");
    }
  }, [resolvedTheme]);

  const isDark = resolvedTheme === "dark";

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          ...(isDark ? DARK_TOKENS : LIGHT_TOKENS),
          ...SHARED_TOKENS,
        },
        algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
      }}
    >
      <AntdApp>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </AntdApp>
    </ConfigProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemedApp />
  </StrictMode>,
);