import { useCallback, useEffect, useRef, useState } from "react";
import { Command } from "cmdk";
import { useNavigate } from "react-router-dom";
import { apiClient } from "@/api/client";

// ─── 命令注册表 ────────────────────────────────────────
interface CommandEntry {
  id: string;
  label: string;
  group: string;
  keywords?: string[];
  action: () => void;
}

const NAV_COMMANDS: CommandEntry[] = [
  { id: "nav:tracked-assets", label: "追踪标的", group: "页面跳转", keywords: ["assets", "tracked", "标的"], action: () => {} },
  { id: "nav:asset-detail", label: "标的详情", group: "页面跳转", keywords: ["detail", "detail", "行情"], action: () => {} },
  { id: "nav:ai-reports", label: "AI 报告", group: "页面跳转", keywords: ["ai", "report", "报告", "分析"], action: () => {} },
  { id: "nav:portfolio", label: "投资组合", group: "页面跳转", keywords: ["portfolio", "持仓", "组合"], action: () => {} },
  { id: "nav:news", label: "新闻列表", group: "页面跳转", keywords: ["news", "新闻", "资讯"], action: () => {} },
  { id: "nav:task-status", label: "任务状态", group: "页面跳转", keywords: ["task", "status", "任务", "定时"], action: () => {} },
  { id: "nav:settings", label: "系统配置", group: "页面跳转", keywords: ["settings", "配置", "设置"], action: () => {} },
];

const TRIGGER_COMMANDS: CommandEntry[] = [
  { id: "trigger:quote", label: "触发行情采集", group: "定时任务", keywords: ["quote", "行情", "报价"], action: () => {} },
  { id: "trigger:daily_close", label: "触发日线采集", group: "定时任务", keywords: ["daily", "close", "日线", "收盘"], action: () => {} },
  { id: "trigger:news", label: "触发新闻采集", group: "定时任务", keywords: ["news", "新闻"], action: () => {} },
  { id: "trigger:ai_report", label: "触发 AI 报告生成", group: "定时任务", keywords: ["ai", "report", "报告", "生成"], action: () => {} },
  { id: "trigger:cleanup", label: "触发数据清理", group: "定时任务", keywords: ["cleanup", "清理", "raw data"], action: () => {} },
];

const ROUTE_MAP: Record<string, string> = {
  "nav:tracked-assets": "/tracked-assets",
  "nav:asset-detail": "/asset-detail",
  "nav:ai-reports": "/ai-reports",
  "nav:portfolio": "/portfolio",
  "nav:news": "/news",
  "nav:task-status": "/task-status",
  "nav:settings": "/settings",
};

const TASK_MAP: Record<string, string> = {
  "trigger:quote": "quote",
  "trigger:daily_close": "daily_close",
  "trigger:news": "news",
  "trigger:ai_report": "ai_report",
  "trigger:cleanup": "cleanup",
};

// ─── 最近使用命令 ──────────────────────────────────────
const RECENT_KEY = "marketlens:command-palette:recent";
const MAX_RECENT = 5;

function loadRecent(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function saveRecent(id: string) {
  const prev = loadRecent().filter((r) => r !== id);
  localStorage.setItem(RECENT_KEY, JSON.stringify([id, ...prev].slice(0, MAX_RECENT)));
}

// ─── 组件 ──────────────────────────────────────────────
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [assetResults, setAssetResults] = useState<Array<{ id: number; symbol: string; name: string | null }>>([]);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const searchTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Cmd/Ctrl+K 快捷键
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // 搜索资产（防抖 200ms）
  useEffect(() => {
    if (!open) {
      setSearch("");
      setAssetResults([]);
      return;
    }
    if (!search.trim()) {
      setAssetResults([]);
      return;
    }
    if (searchTimer.current !== undefined) clearTimeout(searchTimer.current);
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const { data } = await apiClient.get("/assets", { params: { search, page: 1, page_size: 10 } });
        setAssetResults(data.items ?? []);
      } catch {
        setAssetResults([]);
      } finally {
        setLoading(false);
      }
    }, 200);
    searchTimer.current = timer;
    return () => clearTimeout(timer);
  }, [open, search]);

  const executeCommand = useCallback(
    (entry: CommandEntry) => {
      saveRecent(entry.id);
      const route = ROUTE_MAP[entry.id];
      if (route) {
        navigate(route);
      }
      const taskName = TASK_MAP[entry.id];
      if (taskName) {
        apiClient.post(`/tasks/trigger/${taskName}`).catch(() => {});
        // 跳到任务状态页看结果
        navigate("/task-status");
      }
      setOpen(false);
    },
    [navigate],
  );

  const navigateToAsset = useCallback(
    (assetId: number) => {
      saveRecent(`asset:${assetId}`);
      navigate(`/asset-detail?assetId=${assetId}`);
      setOpen(false);
    },
    [navigate],
  );

  const recentIds = loadRecent();

  // 构建完整命令列表：最近使用 + 导航 + 触发任务
  const recentCommands = recentIds
    .filter((id) => !id.startsWith("asset:"))
    .map((id) => [...NAV_COMMANDS, ...TRIGGER_COMMANDS].find((c) => c.id === id))
    .filter(Boolean) as CommandEntry[];

  const allCommands = [...NAV_COMMANDS, ...TRIGGER_COMMANDS];

  // 按分组归类
  const grouped: Record<string, CommandEntry[]> = {};
  if (recentCommands.length > 0) {
    grouped["最近使用"] = recentCommands;
  }
  for (const cmd of allCommands) {
    (grouped[cmd.group] ??= []).push(cmd);
  }

  return (
    <Command.Dialog open={open} onOpenChange={setOpen} label="命令面板" className="command-palette">
      {/* 遮罩 */}
      <div className="command-palette-overlay" onClick={() => setOpen(false)} />

      {/* 容器 */}
      <div className="command-palette-container">
        <Command.Input placeholder="搜索页面、资产或输入命令…" value={search} onValueChange={setSearch} />
        <Command.List>
          <Command.Empty>{search ? "无匹配结果" : "输入关键词开始搜索"}</Command.Empty>
          {loading && <Command.Loading>搜索中…</Command.Loading>}

          {/* 资产搜索结果 */}
          {assetResults.length > 0 && (
            <Command.Group heading="资产搜索">
              {assetResults.map((a) => (
                <Command.Item key={`asset:${a.id}`} onSelect={() => navigateToAsset(a.id)}>
                  {a.symbol} {a.name ?? ""}
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {/* 注册命令 */}
          {Object.entries(grouped).map(([group, cmds]) => (
            <Command.Group key={group} heading={group}>
              {cmds.map((cmd) => (
                <Command.Item key={cmd.id} onSelect={() => executeCommand(cmd)} keywords={cmd.keywords}>
                  {cmd.label}
                </Command.Item>
              ))}
            </Command.Group>
          ))}
        </Command.List>

        <div className="command-palette-footer">
          <kbd>↑↓</kbd> 导航 <kbd>↵</kbd> 执行 <kbd>Esc</kbd> 关闭
        </div>
      </div>
    </Command.Dialog>
  );
}