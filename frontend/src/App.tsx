import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { lazy, Suspense } from "react";
import { Spin } from "antd";
import { AppLayout } from "@/components/layout/AppLayout";
import { MotionPage } from "@/components/shared/MotionPage";

// 路由级懒加载：避免单页面错误导致整站空白
const SettingsPage = lazy(() => import("@/pages/Settings"));
const NewsListPage = lazy(() => import("@/pages/NewsList"));

function withSuspense(Page: React.ComponentType) {
  return (
    <Suspense fallback={<Spin tip="加载中…" />}>
      <MotionPage>
        <Page />
      </MotionPage>
    </Suspense>
  );
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/tracked-assets" replace /> },
      { path: "/tracked-assets", element: withSuspense(SettingsPage) },
      { path: "/asset-detail", element: withSuspense(SettingsPage) },
      { path: "/ai-reports", element: withSuspense(SettingsPage) },
      { path: "/portfolio", element: withSuspense(SettingsPage) },
      { path: "/news", element: withSuspense(NewsListPage) },
      { path: "/task-status", element: withSuspense(SettingsPage) },
      { path: "/settings", element: withSuspense(SettingsPage) },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
