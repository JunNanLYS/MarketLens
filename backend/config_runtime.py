"""运行时配置存储。

设计目标：
- 启动时从 config.yaml 加载一次到内存（dict），后续所有读取走内存。
- 提供 get/set 接口；set 时校验 + 写回 yaml + 通知 reload 钩子。
- 支持的 key 范围（白名单，避免误改 unknown key）：
    - sources.<name>.enabled        (bool)
    - sources.<name>.timeout        (int, >0)
    - scheduler.tasks.<name>.interval (int, >0)
    - apikeys.<name>.api_key        (str, non-empty)
    - apikeys.<name>.endpoint       (str)

YAML 写回采用 atomic 模式：先写 config.yaml.tmp，再 os.replace 覆盖。
覆盖前保留最近一次 config.yaml → config.yaml.bak，便于一键回滚。
"""

from __future__ import annotations

import os
import shutil
import threading
from typing import Any, Callable

import yaml
from loguru import logger

from backend.config import _CONFIG_PATH


class ConfigStoreError(ValueError):
    """配置写入/校验失败时抛出，HTTP 层映射为 400/422。"""


class ConfigStore:
    """单例：进程内维护当前生效配置 + yaml 写回 + reload 钩子。"""

    _instance: "ConfigStore | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "ConfigStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._cfg: dict = {}
        self._write_lock = threading.Lock()
        self._reload_hooks: list[Callable[[dict], None]] = []
        self._load_from_yaml()

    # ─── 加载 ──────────────────────────────────────────────
    def _load_from_yaml(self) -> None:
        with _CONFIG_PATH.open("r", encoding="utf-8") as f:
            self._cfg = yaml.safe_load(f) or {}
        logger.info("ConfigStore 已从 {} 加载配置", _CONFIG_PATH)

    # ─── 读取 ──────────────────────────────────────────────
    def get(self, dotted_key: str, default: Any = None) -> Any:
        """按点分键读取，如 'sources.sina.enabled'。"""
        cur: Any = self._cfg
        for part in dotted_key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def snapshot(self) -> dict:
        """返回当前配置的浅拷贝（防止外部直接改 _cfg）。"""
        return dict(self._cfg)

    # ─── 写入 ──────────────────────────────────────────────
    def update(self, updates: dict) -> dict:
        """应用一组 nested-dict 形式的更新，校验后写回 yaml，触发 reload 钩子。

        Args:
            updates: nested dict，如 {"scheduler": {"tasks": {"quote": {"interval": 1}}}}
                     适合纯 dict 路径。

        Returns:
            更新后的整份配置 dict。

        Raises:
            ConfigStoreError: 路径非法 / 写盘失败
        """
        with self._write_lock:
            new_cfg = self._deepcopy(self._cfg)
            self._deep_merge(new_cfg, updates)
            self._atomic_write_yaml(new_cfg)
            self._cfg = new_cfg
            for hook in list(self._reload_hooks):
                try:
                    hook(new_cfg)
                except Exception:
                    logger.exception("reload hook 失败：{}", hook)
            logger.info("ConfigStore 已应用 nested-dict 更新")
            return dict(new_cfg)

    def update_with_special_handling(self, updates: dict[str, Any]) -> dict:
        """支持两类 key 的高级 update：

        1. data_sources.<group>.<name>     → 整条 source dict（list 中按 name 替换）
        2. scheduler.tasks.<task>.<field>  → scheduler.tasks.<task>.<field> 标量
        3. data_sources.<group>.<name>.<field> → 在 list of dicts 中按 name 定位后改单字段

        处理流程：先把所有变更合并成 (key → value) flat map，分类处理后写回。
        """
        with self._write_lock:
            new_cfg = self._deepcopy(self._cfg)

            for key, value in updates.items():
                self._validate_key_root(key)
                if key.startswith("data_sources."):
                    self._apply_data_sources_change(new_cfg, key, value)
                elif key.startswith("scheduler.tasks."):
                    self._apply_scheduler_change(new_cfg, key, value)
                else:
                    raise ConfigStoreError(f"key 路径不支持：{key}")

            self._atomic_write_yaml(new_cfg)
            self._cfg = new_cfg
            for hook in list(self._reload_hooks):
                try:
                    hook(new_cfg)
                except Exception:
                    logger.exception("reload hook 失败：{}", hook)
            logger.info("ConfigStore 已应用 {} 项更新", len(updates))
            return dict(new_cfg)

    # data_sources entry 允许编辑的字段白名单（避免误传 garbage 字段进 yaml）
    _ALLOWED_SOURCE_FIELDS: frozenset[str] = frozenset(
        {"enabled", "timeout", "optional"}
    )

    @staticmethod
    def _apply_data_sources_change(cfg: dict, key: str, value: Any) -> None:
        """处理 data_sources.<group>.<name>[.<field>] 形式的变更。

        支持：
        - 整条替换：data_sources.structured.sina → {enabled: false, timeout: 30, ...}
        - 单字段：  data_sources.structured.sina.enabled → false

        整条替换的 value dict 字段必须在 ``_ALLOWED_SOURCE_FIELDS`` 白名单内，
        且每个字段都会过 ``_validate_value`` 做类型/范围校验；``params``（命令/URL/token）
        从原 dict 沿用，不接受前端覆写。
        """
        parts = key.split(".")
        # data_sources.structured.sina  (length 3)  整条替换
        # data_sources.structured.sina.enabled  (length 4)  单字段
        if len(parts) == 3:
            _, group, name = parts
            field = None
        elif len(parts) == 4:
            _, group, name, field = parts
        else:
            raise ConfigStoreError(f"key 格式错误：{key}（应为 data_sources.<group>.<name>[.<field>]）")

        items = cfg.setdefault("data_sources", {}).setdefault(group, [])
        if not isinstance(items, list):
            raise ConfigStoreError(f"data_sources.{group} 不是 list")

        # 找/建 dict
        target = next((it for it in items if isinstance(it, dict) and it.get("name") == name), None)
        if target is None:
            if field is not None:
                raise ConfigStoreError(f"data_sources.{group} 中找不到 name={name}")
            target = {"name": name}
            items.append(target)

        if field is None:
            # 整条替换：白名单校验 + 逐字段类型校验，避免 garbage 字段污染 yaml
            if not isinstance(value, dict):
                raise ConfigStoreError(
                    f"{key} 的 value 必须是 dict（当前 {type(value).__name__}）"
                )
            unknown = set(value.keys()) - ConfigStore._ALLOWED_SOURCE_FIELDS
            if unknown:
                raise ConfigStoreError(
                    f"{key} 的 value 含未允许字段：{sorted(unknown)}；"
                    f"仅允许 {sorted(ConfigStore._ALLOWED_SOURCE_FIELDS)}"
                )
            for k_, v_ in value.items():
                ConfigStore._validate_value(f".{k_}", v_)
            new_entry = {"name": name, **value}
            # 保留 params（命令/URL/token）避免被覆盖丢失
            if "params" in target:
                new_entry.setdefault("params", target["params"])
            # 保留 provider（class 名映射，不属用户可编辑范围）
            if "provider" in target:
                new_entry.setdefault("provider", target["provider"])
            target.clear()
            target.update(new_entry)
        else:
            # 单字段
            if field not in ConfigStore._ALLOWED_SOURCE_FIELDS:
                raise ConfigStoreError(
                    f"{key} 字段不允许编辑；仅允许 {sorted(ConfigStore._ALLOWED_SOURCE_FIELDS)}"
                )
            ConfigStore._validate_value(f".{field}", value)
            target[field] = value

    @staticmethod
    def _apply_scheduler_change(cfg: dict, key: str, value: Any) -> None:
        """处理 scheduler.tasks.<task>.<field> 形式的变更。"""
        # scheduler.tasks.quote.interval → 4 段
        parts = key.split(".")
        if len(parts) != 4:
            raise ConfigStoreError(f"key 格式错误：{key}（应为 scheduler.tasks.<task>.<field>）")
        _, _, task_name, field = parts
        if field not in {"interval", "cron"}:
            raise ConfigStoreError(
                f"{key} 字段不允许编辑；仅允许 'interval' / 'cron'"
            )
        if field == "interval":
            ConfigStore._validate_value(f".{field}", value)
        else:  # cron
            if not isinstance(value, str) or not value.strip():
                raise ConfigStoreError(f"{key} 必须是非空字符串，收到 {value!r}")
        cfg.setdefault("scheduler", {}).setdefault("tasks", {}).setdefault(task_name, {})[field] = value

    @staticmethod
    def _validate_key_root(key: str) -> None:
        """白名单根前缀。"""
        allowed = ("data_sources.", "scheduler.tasks.")
        if not any(key.startswith(p) for p in allowed):
            raise ConfigStoreError(
                f"配置 key 不在白名单：{key}（允许前缀：{', '.join(allowed)}）"
            )

    @staticmethod
    def _deep_merge(target: dict, source: dict) -> None:
        """就地深合并：source 中的 dict 递归合并到 target，标量直接覆盖。"""
        for k, v in source.items():
            if isinstance(v, dict) and isinstance(target.get(k), dict):
                ConfigStore._deep_merge(target[k], v)
            else:
                target[k] = v

    def rollback_from_backup(self) -> dict:
        """从 .bak 恢复 yaml，触发 reload。"""
        bak_path = _CONFIG_PATH.with_suffix(_CONFIG_PATH.suffix + ".bak")
        if not bak_path.exists():
            raise ConfigStoreError(f"备份文件不存在：{bak_path}")
        with self._write_lock:
            shutil.copy2(bak_path, _CONFIG_PATH)
            self._load_from_yaml()
            for hook in list(self._reload_hooks):
                try:
                    hook(self._cfg)
                except Exception:
                    logger.exception("rollback hook 失败：{}", hook)
        logger.warning("ConfigStore 已从备份回滚")
        return dict(self._cfg)

    # ─── 钩子 ──────────────────────────────────────────────
    def register_reload_hook(self, hook: Callable[[dict], None]) -> None:
        """注册 reload 钩子。Scheduler / Provider 在此接收配置变更通知。"""
        self._reload_hooks.append(hook)

    # ─── 私有辅助 ──────────────────────────────────────────
    @staticmethod
    def _deepcopy(obj: Any) -> Any:
        # 用 yaml 序列化做深拷贝（避免引入 copy 依赖并能精确还原 yaml 格式）
        return yaml.safe_load(yaml.safe_dump(obj, allow_unicode=True)) or {}

    @staticmethod
    def _validate_value(key: str, value: Any) -> None:
        # 类型 + 范围校验
        if key.endswith(".interval") or key.endswith(".timeout"):
            if not isinstance(value, int) or value <= 0 or value > 24 * 60:
                raise ConfigStoreError(f"{key} 必须是 1~1440 之间的整数，收到 {value!r}")
        elif key.endswith(".enabled") or key.endswith(".optional"):
            if not isinstance(value, bool):
                raise ConfigStoreError(f"{key} 必须是 bool，收到 {value!r}")
        else:
            # 未识别字段（cron string、command 等）：在 _apply_* 已做字段白名单兜底，
            # 这里再次拦截避免被遗漏的路径写入未校验值
            raise ConfigStoreError(f"{key} 字段不在 ConfigStore 已校验集合中")

    def _atomic_write_yaml(self, new_cfg: dict) -> None:
        """atomic 写：备份旧文件 → 写 tmp → rename 覆盖。"""
        bak = _CONFIG_PATH.with_suffix(_CONFIG_PATH.suffix + ".bak")
        tmp = _CONFIG_PATH.with_suffix(_CONFIG_PATH.suffix + ".tmp")
        try:
            # 备份：仅当原文件存在时
            if _CONFIG_PATH.exists():
                shutil.copy2(_CONFIG_PATH, bak)
            with tmp.open("w", encoding="utf-8") as f:
                yaml.safe_dump(
                    new_cfg, f, allow_unicode=True, sort_keys=False, default_flow_style=False
                )
            # 跨平台 atomic
            os.replace(tmp, _CONFIG_PATH)
        except Exception as exc:
            # 清理 tmp；bak 留作回滚依据
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise ConfigStoreError(f"写回 config.yaml 失败：{exc}") from exc


# 公开访问入口
_store: ConfigStore | None = None


def get_config_store() -> ConfigStore:
    global _store
    if _store is None:
        _store = ConfigStore()
    return _store
