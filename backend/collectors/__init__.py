from loguru import logger

from backend.collectors.base import BaseProvider
from backend.collectors.tencent_news import TencentNewsProvider
from backend.collectors.tencent_news_http import TencentNewsHTTPProvider
from backend.collectors.search_engine import SearchEngineNewsProvider
from backend.collectors.neodata import NeoDataProvider
from backend.collectors.rss import RSSProvider
from backend.collectors.sina_news import SinaNewsProvider
from backend.collectors.sina import SinaProvider
from backend.collectors.westock import WeStockProvider

PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "WeStockProvider": WeStockProvider,
    "SinaProvider": SinaProvider,
    "RSSProvider": RSSProvider,
    "NeoDataProvider": NeoDataProvider,
    "TencentNewsProvider": TencentNewsProvider,
    "TencentNewsHTTPProvider": TencentNewsHTTPProvider,
    "SearchEngineNewsProvider": SearchEngineNewsProvider,
    "SinaNewsProvider": SinaNewsProvider,
}


def create_providers(config: dict) -> dict[str, list[BaseProvider]]:
    """根据 config.yaml 中的 data_sources 配置动态实例化 Provider。

    返回 {"structured": [...], "news": [...]} 结构，
    每个列表中的 Provider 按配置顺序排列（即优先级顺序）。
    """
    result: dict[str, list[BaseProvider]] = {"structured": [], "news": []}
    data_sources: dict = config.get("data_sources", {})

    for category in ("structured", "news"):
        sources: list[dict] = data_sources.get(category, [])
        for source_cfg in sources:
            if not source_cfg.get("enabled", True):
                logger.info("数据源已禁用，跳过: {}", source_cfg.get("name", "unknown"))
                continue

            provider_name: str = source_cfg.get("provider", "")
            provider_cls = PROVIDER_REGISTRY.get(provider_name)
            if provider_cls is None:
                logger.error("未注册的 Provider 类: {}, 跳过", provider_name)
                continue

            instance = provider_cls(
                name=source_cfg.get("name", provider_name),
                timeout=source_cfg.get("timeout", 30),
                params=source_cfg.get("params"),
                optional=source_cfg.get("optional", False),
            )
            result[category].append(instance)
            logger.info("已注册 Provider: {} ({})", instance.name, provider_name)

    return result
