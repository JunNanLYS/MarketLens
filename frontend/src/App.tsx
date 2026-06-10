import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { lazy, Suspense } from "react";
import { Spin } from "antd";
import { AppLayout } from "@/components/layout/AppLayout";
import { MotionPage } from "@/components/shared/MotionPage";

// 路由级懒加载：避免单页面错误导致整站空白
const SettingsPage = lazy(() => import("@/pages/Settings"));
const NewsListPage = lazy(() => import("@/pages/NewsList"));
const TaskStatusPage = lazy(() => import("@/pages/TaskStatus"));
const AiReportsPage = lazy(() => import("@/pages/AiReports"));
const TrackedAssetsPage = lazy(() => import("@/pages/TrackedAssets"));
const PortfolioPage = lazy(() => import("@/pages/Portfolio"));
const AssetDetailPage = lazy(() => import("@/pages/AssetDetail"));

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
      { path: "/tracked-assets", element: withSuspense(TrackedAssetsPage) },
      { path: "/asset-detail", element: withSuspense(AssetDetailPage) },
      { path: "/ai-reports", element: withSuspense(AiReportsPage) },
      { path: "/portfolio", element: withSuspense(PortfolioPage) },
      { path: "/news", element: withSuspense(NewsListPage) },
      { path: "/task-status", element: withSuspense(TaskStatusPage) },
      { path: "/settings", element: withSuspense(SettingsPage) },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
