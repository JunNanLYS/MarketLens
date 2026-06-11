import { Button, Result } from "antd";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";

function getRouteErrorMessage(error: unknown): string {
  if (isRouteErrorResponse(error)) {
    if (typeof error.data === "string" && error.data) {
      return error.data;
    }

    if (error.data && typeof error.data === "object") {
      const payload = error.data as { detail?: string; error?: string };
      if (payload.detail) {
        return payload.detail;
      }
      if (payload.error) {
        return payload.error;
      }
    }

    return error.statusText || "请稍后重试";
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return "请刷新页面后重试";
}

// 路由级错误边界：兜住懒加载与页面渲染异常，避免整页白屏。
export function RouteErrorBoundary() {
  const error = useRouteError();

  return (
    <Result
      status="error"
      title={isRouteErrorResponse(error) ? `页面加载失败（${error.status}）` : "页面渲染失败"}
      subTitle={getRouteErrorMessage(error)}
      extra={[
        <Button key="reload" type="primary" onClick={() => window.location.reload()}>
          刷新页面
        </Button>,
        <Button key="home" onClick={() => window.location.assign("/tracked-assets")}>
          返回首页
        </Button>,
      ]}
    />
  );
}
