import {
  Button,
  InputNumber,
  Popconfirm,
  Skeleton,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiClient, extractErrorMessage } from "@/api/client";
import type { SettingsResponse } from "@/api/types";
import { QueryErrorState } from "@/components/shared/QueryErrorState";
import { TASK_LABELS } from "@/utils/constants";
import { SourceTimeoutCell } from "./SourceTimeoutCell";

// 可编辑配置区
// 范围：scheduler.tasks.*.interval（立即生效）+ 数据源只读
// 数据源 enabled/timeout 需重启才能让 Provider registry 重建，所以 PATCH 后只更新 timeout（不重建）。
// 实际：timeout 改的是 per-provider HTTP 客户端超时，下次请求生效；enabled 改会重建 Provider。

/** 设置变更后必须失效的 queryKey（settings 自身 + 相关调度任务）。 */
const SETTING_MUTATION_INVALIDATE_KEYS: readonly string[][] = [
  ["settings", "editable"],
  ["tasks", "status"],
  ["tasks", "logs"],
];

/** 共用 onError 处理器：弹 message.error 带 "X 失败：..." 文案。 */
function onSettingError(label: string) {
  return (err: unknown) => {
    message.error(`${label}失败：${extractErrorMessage(err)}`);
  };
}

function invalidateSettingQueries(queryClient: ReturnType<typeof useQueryClient>) {
  for (const key of SETTING_MUTATION_INVALIDATE_KEYS) {
    queryClient.invalidateQueries({ queryKey: key });
  }
}

export function EditableSettingsCard() {
  const queryClient = useQueryClient();

  const settings = useQuery<SettingsResponse>({
    queryKey: ["settings", "editable"],
    queryFn: async () => {
      const { data } = await apiClient.get<SettingsResponse>("/settings");
      return data;
    },
    staleTime: 30_000,
  });

  const [editingTask, setEditingTask] = useState<string | null>(null);
  const [newInterval, setNewInterval] = useState<number | null>(null);

  const updateInterval = useMutation({
    mutationFn: async ({ task, interval }: { task: string; interval: number }) => {
      await apiClient.patch("/settings", {
        updates: { [`scheduler.tasks.${task}.interval`]: interval },
      });
    },
    onSuccess: (_data, { task, interval }) => {
      message.success(`已更新 ${TASK_LABELS[task] ?? task} 频率：每 ${interval} 分钟`);
      setEditingTask(null);
      setNewInterval(null);
      invalidateSettingQueries(queryClient);
    },
    onError: onSettingError("更新"),
  });

  const rollback = useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<SettingsResponse>("/settings/rollback");
      return data;
    },
    onSuccess: () => {
      message.success("已从备份回滚");
      invalidateSettingQueries(queryClient);
    },
    onError: onSettingError("回滚"),
  });

  // 数据源启用/禁用/超时变更：PATCH 立即生效（后端重建 Provider）
  const updateSource = useMutation({
    mutationFn: async (params: { group: string; name: string; updates: Record<string, unknown> }) => {
      const keyPrefix = `data_sources.${params.group}.${params.name}`;
      const updates: Record<string, unknown> = {};
      for (const [field, value] of Object.entries(params.updates)) {
        updates[`${keyPrefix}.${field}`] = value;
      }
      await apiClient.patch("/settings", { updates });
    },
    onSuccess: (_data, { group, name, updates }) => {
      const fields = Object.keys(updates).map((f) => f.split(".").pop()).join(", ");
      message.success(`已更新 ${group}/${name}：${fields}（Provider 已重建）`);
      invalidateSettingQueries(queryClient);
    },
    onError: onSettingError("更新"),
  });

  if (settings.isLoading) return <Skeleton active />;
  if (settings.isError) {
    return <QueryErrorState error={settings.error} onRetry={settings.refetch} />;
  }

  const tasks = settings.data?.editable.scheduler.tasks ?? {};
  const sources = settings.data?.editable.sources ?? [];

  return (
    <Space direction="vertical" size="middle" className="w-full">
      <div>
        <Space style={{ marginBottom: 8 }}>
          <Typography.Text strong>采集任务频率</Typography.Text>
          <Tooltip title="点保存后立即生效（APScheduler 重注册任务）">
            <Typography.Text type="secondary" className="text-xs">ⓘ 立即生效</Typography.Text>
          </Tooltip>
        </Space>
        <Table
          size="small"
          rowKey="name"
          pagination={false}
          dataSource={Object.entries(tasks).map(([name, t]) => ({ name, ...t }))}
          columns={[
            {
              title: "任务",
              dataIndex: "name",
              render: (n: string) => TASK_LABELS[n] ?? n,
            },
            {
              title: "类型",
              dataIndex: "interval",
              width: 100,
              render: (v: number | null) =>
                v != null ? <Tag color="blue">interval</Tag> : <Tag>cron</Tag>,
            },
            {
              title: "当前值",
              key: "current",
              render: (_: unknown, r) =>
                r.interval != null ? `每 ${r.interval} 分钟` : r.cron ?? "—",
            },
            {
              title: "操作",
              key: "action",
              width: 280,
              render: (_: unknown, r) => {
                if (r.interval == null) {
                  return <Typography.Text type="secondary" className="text-xs">cron 暂不开放</Typography.Text>;
                }
                const isEditing = editingTask === r.name;
                return isEditing ? (
                  <Space>
                    <InputNumber
                      size="small"
                      min={1}
                      max={1440}
                      value={newInterval}
                      onChange={(v) => setNewInterval(typeof v === "number" ? v : null)}
                      style={{ width: 110 }}
                      addonAfter="分钟"
                    />
                    <Button
                      type="primary"
                      size="small"
                      loading={updateInterval.isPending}
                      onClick={() =>
                        newInterval != null &&
                        updateInterval.mutate({ task: r.name, interval: newInterval })
                      }
                    >
                      保存
                    </Button>
                    <Button size="small" onClick={() => { setEditingTask(null); setNewInterval(null); }}>
                      取消
                    </Button>
                  </Space>
                ) : (
                  <Button
                    size="small"
                    onClick={() => { setEditingTask(r.name); setNewInterval(r.interval); }}
                  >
                    修改
                  </Button>
                );
              },
            },
          ]}
        />
      </div>

      <div>
        <Space style={{ marginBottom: 8 }}>
          <Typography.Text strong>数据源</Typography.Text>
          <Tooltip title="启用/禁用 / 修改超时：点保存后后端立即重建 Provider 列表生效">
            <Typography.Text type="secondary" className="text-xs">ⓘ 立即生效</Typography.Text>
          </Tooltip>
        </Space>
        <Table
          size="small"
          rowKey={(r) => `${r.group}-${r.name}`}
          pagination={false}
          dataSource={sources}
          columns={[
            { title: "分组", dataIndex: "group", width: 100 },
            { title: "名称", dataIndex: "name" },
            { title: "Provider", dataIndex: "provider" },
            {
              title: "启用",
              dataIndex: "enabled",
              width: 90,
              render: (v: boolean, record) => {
                const isPending =
                  updateSource.isPending &&
                  updateSource.variables?.group === record.group &&
                  updateSource.variables?.name === record.name &&
                  "enabled" in (updateSource.variables?.updates ?? {});
                return (
                  <Switch
                    size="small"
                    checked={v}
                    disabled={isPending}
                    onChange={(checked) =>
                      updateSource.mutate({
                        group: record.group,
                        name: record.name,
                        updates: { enabled: checked },
                      })
                    }
                  />
                );
              },
            },
            {
              title: "可选",
              dataIndex: "optional",
              width: 70,
              render: (v: boolean) => (v ? "是" : "★ 必需"),
            },
            {
              title: "超时(s)",
              dataIndex: "timeout",
              width: 180,
              render: (v: number, record) => (
                <SourceTimeoutCell
                  value={v}
                  group={record.group}
                  name={record.name}
                  isPending={
                    updateSource.isPending &&
                    updateSource.variables?.group === record.group &&
                    updateSource.variables?.name === record.name &&
                    "timeout" in (updateSource.variables?.updates ?? {})
                  }
                  onSave={(newValue) =>
                    updateSource.mutate({
                      group: record.group,
                      name: record.name,
                      updates: { timeout: newValue },
                    })
                  }
                />
              ),
            },
          ]}
        />
      </div>

      <Space>
        <Popconfirm
          title="从 .bak 恢复最近一次修改？"
          description="所有未回滚的更改会丢失"
          okText="确认回滚"
          cancelText="取消"
          onConfirm={() => rollback.mutate()}
        >
          <Button danger loading={rollback.isPending}>
            ↩ 从备份回滚
          </Button>
        </Popconfirm>
      </Space>
    </Space>
  );
}
