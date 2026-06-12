import type { CSSProperties } from "react";
import { Button, Result } from "antd";
import { extractErrorMessage } from "@/api/client";

interface Props {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  style?: CSSProperties;
  className?: string;
}

interface ErrorMeta {
  title: string;
  subtitle: string;
  icon: string;
}

// 从 error 对象推断 HTTP 状态/错误类型，映射友好文案
function inferErrorMeta(error: unknown): ErrorMeta {
  const message = extractErrorMessage(error);

  // axios 风格错误对象
  const axiosErr = error as
    | {
        response?: { status?: number };
        code?: string;
      }
    | undefined;

  const status = axiosErr?.response?.status;
  const code = axiosErr?.code;

  if (status === 401) {
    return {
      title: "API Key 无效",
      subtitle: "请在系统配置中检查 API Key 是否正确。",
      icon: "🔑",
    };
  }
  if (status === 404) {
    return {
      title: "资源不存在",
      subtitle: message || "请求的资源已被删除或不存在。",
      icon: "🔍",
    };
  }
  if (status === 422) {
    return {
      title: "参数无效",
      subtitle: message || "请求参数有误，请检查后重试。",
      icon: "📋",
    };
  }
  if (status === 500) {
    return {
      title: "服务器异常",
      subtitle: message || "后端服务发生异常，请稍后重试。",
      icon: "⚠️",
    };
  }
  if (status === 502 || status === 503 || status === 504) {
    return {
      title: "服务暂不可用",
      subtitle: "后端服务暂时无法访问，请稍后重试。",
      icon: "🚧",
    };
  }
  if (code === "ECONNABORTED" || /timeout/i.test(message)) {
    return {
      title: "请求超时",
      subtitle: "网络请求超时，请稍后重试。",
      icon: "⏱️",
    };
  }
  if (code === "ERR_NETWORK" || /network/i.test(message)) {
    return {
      title: "网络连接失败",
      subtitle: "无法连接到后端服务，请检查网络。",
      icon: "📡",
    };
  }
  return {
    title: "加载失败",
    subtitle: message || "发生未知错误，请稍后重试。",
    icon: "⚠️",
  };
}

/**
 * 统一 API 错误展示（DESIGN.md §4.13）：
 * - 根据 HTTP 状态码 / axios error code 推断错误类型，给出针对性文案
 * - 居中布局，padding 48px
 * - antd Result + 自定义 emoji icon + 重试按钮（type="primary" 实心）
 * 替代 7 page 散落的 `<Text danger>` 错误展示
 */
export function QueryErrorState({ error, onRetry, title, style, className }: Props) {
  const meta = inferErrorMeta(error);
  return (
    <Result
      status="error"
      title={title ?? meta.title}
      subTitle={meta.subtitle}
      icon={<span style={{ fontSize: 48, lineHeight: 1 }}>{meta.icon}</span>}
      extra={
        onRetry ? (
          <Button type="primary" onClick={onRetry}>
            重试
          </Button>
        ) : null
      }
      style={style}
      className={className}
    />
  );
}
