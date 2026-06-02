from loguru import logger

from backend.collectors.base import BaseProvider
from backend.collectors.tencent_news import TencentNewsProvider
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
    "SearchEngineNewsProvider": SearchEngineNewsProvider,
    "SinaNewsProvider": SinaNewsProvider,
}

def create_providers(config):
    from loguru import logger
    result = {'structured': [], 'news': []}
    data_sources = config.get('data_sources', {})
    for category in ('structured', 'news'):
        sources = data_sources.get(category, [])
        for source_cfg in sources:
            if not source_cfg.get('enabled', True):
                logger.info('disabled: {}', source_cfg.get('name', 'unknown'))
                continue
            provider_name = source_cfg.get('provider', '')
            provider_cls = PROVIDER_REGISTRY.get(provider_name)
            if provider_cls is None:
                logger.error('unregistered: {}', provider_name)
                continue
            instance = provider_cls(
                name=source_cfg.get('name', provider_name),
                timeout=source_cfg.get('timeout', 30),
                params=source_cfg.get('params'),
                optional=source_cfg.get('optional', False),
            )
            result[category].append(instance)
            logger.info('{} ({})', instance.name, provider_name)
    return result
