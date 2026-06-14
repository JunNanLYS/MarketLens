"""Template mixin for CollectionService: generic collect-with-lock methods."""

import asyncio

from loguru import logger

from backend.services._collection._core import _WRITE_LOCK
from backend.storage.database import get_connection_sync


class _CollectionTemplateMixin:
    """模板方法：_run_collect_with_lock / _run_collect_multi_with_lock。"""

    async def _run_collect_with_lock(
        self,
        target: str | None,
        provider_method_name: str,
        payload_builder,
        insert_fn,
        provider_args: dict | None = None,
        validate_fn=None,
        error_label: str = "数据",
        abort_on_invalid: bool = False,
    ):
        """采集 + 落库公共流程（供 19 个 collect_* 公开方法复用）。

        模板步骤：
        1. 遍历所有结构化 Provider，跳过非 WeStockProvider；
        2. 调用 provider.{provider_method_name}(target or **provider_args)；
           target=None 时只传 provider_args（适用于 board_sectors / hot_sectors 无参方法）；
        3. 用 validate_fn(data) 校验（默认 truthy）；
           - 通过 → 进入落库流程；
           - 不通过 + abort_on_invalid=False → 试下一个 provider；
           - 不通过 + abort_on_invalid=True → 立即 return None（不再尝试）；
        4. 调 payload_builder(data, source, collected_at) 组装 payload；
        5. 持 _WRITE_LOCK + sync 连接，调用 insert_fn(conn, payload)，commit + close；
        6. 返回 data（provider 方法的原始结果）；
        7. 整 provider 循环跑完未返回 → None。

        Args:
            target: 标的代码 / 市场名 / 任意标识；透传给 provider 方法作第一个位置参数；
                None 时只透传 provider_args（如 board_sectors 无参方法）。
            provider_method_name: provider 实例上调用的方法名（如 "etf_info"）。
            payload_builder: 闭包 (data, source, collected_at) -> dict；
                payload 必须含 "raw_packets" 列表 + "row"（单条）或 "rows"（多条）。
            insert_fn: 落库的 staticmethod 引用（_insert_etf_basic 等）。
            provider_args: 透传给 provider 方法的额外 kwargs。
            validate_fn: 数据校验函数；None 时默认用 bool(data) 判空。
            error_label: 异常日志里的中文数据名（如 "ETF 基础信息"）。
            abort_on_invalid: 校验失败时是"试下一个 provider"（False）还是"立即返回 None"（True）；
                旧 collect_* 多用前者（try all providers），新 etf/chip/margintrade 等用后者。
        """
        validator = validate_fn if validate_fn is not None else (lambda d: bool(d))
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                method = getattr(provider, provider_method_name)
                if target is None:
                    data = await method(**(provider_args or {}))
                else:
                    data = await method(target, **(provider_args or {}))
                if not validator(data):
                    if abort_on_invalid:
                        return None
                    continue
                collected_at = self._now_iso()
                source = provider.name
                payload = payload_builder(data, source, collected_at)
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        insert_fn(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return data
            except Exception as e:
                logger.warning(
                    "Provider {} 采集{}失败: {} - {}",
                    provider.name,
                    error_label,
                    target,
                    e,
                )
                continue
        return None

    async def _run_collect_multi_with_lock(
        self,
        target: str,
        provider_method_name: str,
        ftype_arg: str,
        payload_builder,
        insert_fn,
        provider_args: dict | None = None,
        ftype_values: tuple[str, ...] = ("income", "balance", "cashflow"),
        error_label: str = "数据",
    ):
        """采集 + 落库公共流程（多子任务并发版，供 collect_us_finance / collect_hk_finance 复用）。

        与 _run_collect_with_lock 的区别：单次 provider 调用内
        用 asyncio.gather 并发调 3 个 ftype（如 income/balance/cashflow），
        合并子结果（return_exceptions=True 隔离单 ftype 失败）→ 校验 → 落库。

        provider 方法签名：await provider.{method}(target, ftype=<ftype>, **provider_args)
        """
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                method = getattr(provider, provider_method_name)
                results = await asyncio.gather(
                    *(
                        method(target, **{ftype_arg: ft, **(provider_args or {})})
                        for ft in ftype_values
                    ),
                    return_exceptions=True,
                )
                all_items: list[dict] = []
                for items in results:
                    if isinstance(items, Exception):
                        logger.warning("{} 子任务失败: {}", provider_method_name, items)
                        continue
                    if items:
                        all_items.extend(items)
                if not all_items:
                    return None
                collected_at = self._now_iso()
                source = provider.name
                payload = payload_builder(all_items, source, collected_at)
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        insert_fn(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return all_items
            except Exception as e:
                logger.warning(
                    "Provider {} 采集{}失败: {} - {}",
                    provider.name,
                    error_label,
                    target,
                    e,
                )
                continue
        return None
