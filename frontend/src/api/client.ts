import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { message } from "antd";
import { useApiKeyStore } from "@/auth/apiKeyStore";

// Axios 实例：baseURL、拦截器注入 X-API-Key、401 处理
export const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 30_000,
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const key = useApiKeyStore.getState().key;
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
      message.error("API Key 无效，请在系统配置页重新设置");
    }
    return Promise.reject(error);
  },
);

// 错误处理：把后端 {error, detail} 形式解析为可读错误
export function extractErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { detail?: string; error?: string } | undefined;
    return data?.detail || data?.error || err.message;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}
