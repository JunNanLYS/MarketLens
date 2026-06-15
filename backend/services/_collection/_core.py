"""Core mixin for CollectionService: init, provider lifecycle, write lock."""

from datetime import datetime, timezone

from loguru import logger

from backend.collectors import BaseProvider, create_providers
from backend.collectors.westock import WeStockProvider
from backend.config import get_config
from backend.services.asset_service import AssetService


class _CollectionCoreMixin:
    """核心：构造、Provider 生命周期、westock 白名单判断。"""

    def __init__(self, providers: dict[str, list[BaseProvider]] | None = None) -> None:
        if providers is not None:
            self._providers = providers
        else:
            config = get_config()
            self._providers = create_providers(config)
        self._asset_service = AssetService(providers=self._providers)

    def _get_structured_providers(self) -> list[BaseProvider]:
        return self._providers.get("structured", [])

    async def close_providers(self) -> None:
        """关闭当前服务持有的结构化 Provider 资源。"""
        for provider in self._get_structured_providers():
            try:
                await provider.close()
            except Exception:
                logger.exception("关闭 Provider 失败: {}", provider.name)

    async def reload_providers(self, config: dict) -> None:
        """运行时重建 Provider 列表（用于配置变更后立即生效）。

        Args:
            config: 完整配置 dict（来自 ConfigStore.snapshot()）

        步骤：
        1. 先关掉旧 Provider 的 httpx 客户端 / 子进程，避免泄漏
        2. 用新配置 create_providers 重建
        3. 通过 AssetService.update_providers() 同步替换持有的 provider 列表

        注意：AssetService 与 CollectionService 共享同一 list 引用（非副本），
        本方法关闭 self._providers 时即关闭了 AssetService 持有的旧客户端；
        若未来 AssetService 复制了 list，需在此处双向 close。
        """
        await self.close_providers()
        self._providers = create_providers(config)
        self._asset_service.update_providers(self._providers)
        logger.info(
            "CollectionService Provider 已重建：structured={} 个",
            len(self._get_structured_providers()),
        )

    @staticmethod
    def _is_westock_only(provider) -> bool:
        """判断 provider 是否为 WeStockProvider（用于按数据域白名单 westock 唯一来源）。

        集中判断，避免在 ~34 个 _fetch_* / collect_* 方法中散落 isinstance 硬编码。
        扩展新浪 / Tencent 实现同类数据时改此处即可。
        """
        return isinstance(provider, WeStockProvider)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
