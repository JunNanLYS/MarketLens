"""合并子路由暴露统一 router，保持 `from backend.api.data import router` 兼容。

`_service` 在本 __init__.py 中通过 `from backend.api.data._service import _service`
re-export，供测试 patch `backend.api.data._service` 用。
"""

__all__ = ["router", "_service"]


from fastapi import APIRouter

from backend.api.data._service import _service as _service  # noqa: F401
from backend.api.data.data_etf import router as etf_router
from backend.api.data.data_finance import router as finance_router
from backend.api.data.data_market import router as market_router
from backend.api.data.data_quotes import router as quotes_router

router = APIRouter(prefix="/api/v1/data", tags=["data"])
router.include_router(quotes_router)
router.include_router(finance_router)
router.include_router(etf_router)
router.include_router(market_router)
