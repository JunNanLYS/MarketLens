"""Shared CollectionService singleton for backend.api.data sub-routers.

独立模块避免与 backend.api.data.__init__.py 的循环导入：
子路由（data_etf/data_finance/data_market/data_quotes）通过本模块获取 _service，
而 backend.api.data.__init__.py 仍 re-export `_service` 供测试 patch 用。
"""

from backend.services.collection_service import CollectionService

_service: CollectionService = CollectionService()


def _get_service() -> CollectionService:
    """返回当前 _service（每次访问以支持测试 monkeypatch）。

    抽到本模块避免 4 个子路由各自定义同一函数。
    """
    return _service
