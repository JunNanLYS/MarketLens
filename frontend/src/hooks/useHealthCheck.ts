import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiClient } from "@/api/client";
import type { HealthResponse } from "@/api/types";

function getIsPageVisible(): boolean {
  if (typeof document === "undefined") {
    return true;
  }
  return document.visibilityState === "visible";
}

function usePageVisible(): boolean {
  const [isPageVisible, setIsPageVisible] = useState<boolean>(() => getIsPageVisible());

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }

    const handleVisibilityChange = () => {
      setIsPageVisible(getIsPageVisible());
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  return isPageVisible;
}

// 30s 轮询，对应后端 /health；后台标签页暂停轮询，回到前台后自动恢复
export function useHealthCheck() {
  const isPageVisible = usePageVisible();

  return useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: async () => {
      const { data } = await apiClient.get<HealthResponse>("/health");
      return data;
    },
    refetchInterval: isPageVisible ? 30_000 : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    retry: 0,
  });
}
