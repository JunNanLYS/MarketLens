import { create } from "zustand";
import { persist } from "zustand/middleware";

const DEFAULT_API_KEY = "marketlens-local";

interface ApiKeyState {
  key: string;
  setKey: (key: string) => void;
  clear: () => void;
}

// API Key 仅持久化用户显式设置的值；默认 key 改为运行时回退，不在首次启动时写入 localStorage。
export const useApiKeyStore = create<ApiKeyState>()(
  persist(
    (set) => ({
      key: "",
      setKey: (key) => set({ key }),
      clear: () => set({ key: "" }),
    }),
    { name: "marketlens_api_key" },
  ),
);

export function getApiKey(): string {
  return useApiKeyStore.getState().key || DEFAULT_API_KEY;
}
