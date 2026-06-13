import { lazy, Suspense, useEffect, type ComponentType } from "react";
import { App as AntdApp, Spin } from "antd";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { bindAppMessageApi } from "@/api/client";
import { AppLayout } from "@/components/layout/AppLayout";
import { RouteErrorBoundary } from "@/components/shared/RouteErrorBoundary";

// 路由级懒加载：避免单页面错误导致整站空白。
const SettingsPage = lazy(() => import("@/pages/Settings"));
const NewsListPage = lazy(() => import("@/pages/NewsList"));
const TaskStatusPage = lazy(() => import("@/pages/TaskStatus"));
const AiReportsPage = lazy(() => import("@/pages/AiReports"));
const TrackedAssetsPage = lazy(() => import("@/pages/TrackedAssets"));
const PortfolioPage = lazy(() => import("@/pages/Portfolio"));
const AssetDetailPage = lazy(() => import("@/pages/AssetDetail"));

function AppMessageBridge() {
  const { message } = AntdApp.useApp();

  useEffect(() => {
    bindAppMessageApi(message);
    return () => bindAppMessageApi(null);
  }, [message]);

  return null;
}

// 页面进出场动画已统一移到 AppLayout 的 AnimatePresence，
// 这里只负责 Suspense fallback，避免双层动画叠加。
function withSuspense(Page: ComponentType) {
  return (
    <Suspense fallback={<Spin tip="加载市场数据中…" />}>
      <Page />
    </Suspense>
  );
}

function createPageRoute(path: string, Page: ComponentType) {
  return {
    path,
    element: withSuspense(Page),
    errorElement: <RouteErrorBoundary />,
  };
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    errorElement: <RouteErrorBoundary />,
    children: [
      { index: true, element: <Navigate to="/tracked-assets" replace /> },
      createPageRoute("/tracked-assets", TrackedAssetsPage),
      createPageRoute("/asset-detail", AssetDetailPage),
      createPageRoute("/ai-reports", AiReportsPage),
      createPageRoute("/portfolio", PortfolioPage),
      createPageRoute("/news", NewsListPage),
      createPageRoute("/task-status", TaskStatusPage),
      createPageRoute("/settings", SettingsPage),
    ],
  },
]);

export function App() {
  return (
    <>
      <AppMessageBridge />
      <RouterProvider router={router} />
    </>
  );
}
