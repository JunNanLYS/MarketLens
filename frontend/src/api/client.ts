import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { getApiKey, useApiKeyStore } from "@/auth/apiKeyStore";

interface MessageApiLike {
  error: (content: string) => unknown;
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || "/api/v1";
let appMessageApi: MessageApiLike | null = null;

function emitErrorMessage(content: string): void {
  if (appMessageApi) {
    void appMessageApi.error(content);
    return;
  }

  console.error(content);
}

function stripApiVersionSuffix(pathname: string): string {
  return pathname.replace(/\/api\/v1\/?$/, "") || "/";
}

// 注册由 Ant Design App context 提供的消息实例，避免直接使用静态 message。
export function bindAppMessageApi(messageApi: MessageApiLike | null): void {
  appMessageApi = messageApi;
}

// 统一错误提示出口：优先走 App context，未注册时回退到控制台。
export function showErrorMessage(content: string): void {
  emitErrorMessage(content);
}

// 供布局层展示接口地址；绝对地址显示真实后端，代理模式显示相对基址。
export function getApiBaseUrlLabel(): string {
  if (/^https?:\/\//.test(API_BASE_URL)) {
    const url = new URL(API_BASE_URL);
    const backendPath = stripApiVersionSuffix(url.pathname);
    const normalizedPath = backendPath === "/" ? "" : backendPath.replace(/\/$/, "");
    return `${url.origin}${normalizedPath}`;
  }

  return `同源代理（${API_BASE_URL}）`;
}

// Axios 实例：baseURL、拦截器注入 X-API-Key、401 处理。
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30_000,
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const key = getApiKey();
  if (key) {
    config.headers.set("X-API-Key", key);
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      useApiKeyStore.getState().clear();
      showErrorMessage("API Key 无效，请在系统配置页重新设置");
      return Promise.reject(error);
    }

    // 网络层错误：axios 给的错误码直接判断，不走 4xx/5xx 业务分支
    if (error.code === "ECONNABORTED") {
      showErrorMessage("请求超时，请稍后重试");
      return Promise.reject(error);
    }
    if (error.code === "ERR_NETWORK") {
      showErrorMessage("无法连接到后端");
      return Promise.reject(error);
    }

    // 5xx 服务端异常：与 4xx 业务错误（422 validation 等）严格区分，
    // 业务错误由各页面 extractErrorMessage 自行处理，这里只兜底"非预期"的服务端故障
    const status = error.response?.status;
    if (status === 502 || status === 503 || status === 504) {
      showErrorMessage("后端服务暂不可用");
      return Promise.reject(error);
    }

    return Promise.reject(error);
  },
);

// 错误处理：把后端 {error, detail} 形式解析为可读错误。
export function extractErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { detail?: string; error?: string } | undefined;
    return data?.detail || data?.error || err.message;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}
