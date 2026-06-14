"""数据采集编排服务，负责调度 Provider 采集数据并持久化。

实现采用 Mixin 架构：原 3451 行的单一类已拆分到 `_collection/` 子包，
本文件仅保留 Mixin 组合 + 文档字符串。
"""

from backend.services._collection._collect_public import _CollectionPublicMixin
from backend.services._collection._core import (
    _WRITE_LOCK,
    _CollectionCoreMixin,
)
from backend.services._collection._daily_close import _CollectionDailyCloseMixin
from backend.services._collection._fetch_extended import _CollectionFetchExtendedMixin
from backend.services._collection._fetch_legacy import _CollectionFetchLegacyMixin
from backend.services._collection._helpers import (
    _save_raw_data,
    _with_run_log,
    _CollectionHelpersMixin,
)
from backend.services._collection._insert import _CollectionInsertMixin
from backend.services._collection._quotes import _CollectionQuotesMixin
from backend.services._collection._read import _CollectionReadMixin
from backend.services._collection._template import _CollectionTemplateMixin

__all__ = [
    "CollectionService",
    "_WRITE_LOCK",
    "_save_raw_data",
    "_with_run_log",
]


class CollectionService(
    _CollectionCoreMixin,
    _CollectionHelpersMixin,
    _CollectionTemplateMixin,
    _CollectionQuotesMixin,
    _CollectionDailyCloseMixin,
    _CollectionFetchLegacyMixin,
    _CollectionFetchExtendedMixin,
    _CollectionInsertMixin,
    _CollectionPublicMixin,
    _CollectionReadMixin,
):
    """数据采集编排服务，负责调度 Provider 采集数据并持久化。"""
