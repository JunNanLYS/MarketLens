import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { HealthResponse } from "@/api/types";

// 30s 轮询，对应后端 /health
export function useHealthCheck() {
  return useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: async () => {
      const { data } = await apiClient.get<HealthResponse>("/health");
      return data;
    },
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
    retry: 0,
  });
}
