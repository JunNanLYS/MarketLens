import { create } from "zustand";
import { persist } from "zustand/middleware";

// API Key 持久化在 localStorage；首次启动从后端 config.yaml 默认值 marketlens-local 起步
interface ApiKeyState {
  key: string;
  setKey: (key: string) => void;
  clear: () => void;
}

export const useApiKeyStore = create<ApiKeyState>()(
  persist(
    (set) => ({
      key: "marketlens-local",
      setKey: (key) => set({ key }),
      clear: () => set({ key: "" }),
    }),
    { name: "marketlens_api_key" },
  ),
);
