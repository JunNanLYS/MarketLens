from datetime import datetime, timezone

import httpx
from loguru import logger

from backend.collectors.base import BaseProvider


class NeoDataProvider(BaseProvider):
    """通过 NeoData HTTP API 获取金融数据增强，optional 模式下失败仅记录警告。"""

    def __init__(
        self,
        name: str,
        timeout: int = 20,
        params: dict | None = None,
        optional: bool = True,
    ) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self.endpoint: str = self.params.get("endpoint", "")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _log_error(self, msg: str, **kwargs: object) -> None:
        if self.optional:
            logger.warning(msg, **kwargs)
        else:
            logger.error(msg, **kwargs)

    def _post(self, path: str, payload: dict) -> dict | None:
        url = f"{self.endpoint.rstrip('/')}/{path.lstrip('/')}"
        try:
            resp = httpx.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            self._log_error("NeoData 请求超时: url={}, timeout={}s", url=url, timeout=self.timeout)
            return None
        except httpx.HTTPStatusError as e:
            self._log_error(
                "NeoData HTTP 错误: url={}, status={}",
                url=url,
                status=e.response.status_code,
            )
            return None
        except Exception as e:
            self._log_error("NeoData 请求异常: url={}, error={}", url=url, error=e)
            return None

    def search(self, keyword: str) -> list[dict]:
        data = self._post("search", {"keyword": keyword})
        if data is None:
            return []
        items = data if isinstance(data, list) else data.get("results", [])
        return [
            {
                "symbol": item.get("symbol", ""),
                "name": item.get("name", ""),
                "market": item.get("market", ""),
                "source": "neodata",
                "collected_at": self._now(),
            }
            for item in items
        ]

    def quote(self, symbols: list[str]) -> list[dict]:
        data = self._post("quote", {"symbols": symbols})
        if data is None:
            return []
        items = data if isinstance(data, list) else data.get("results", [])
        return [
            {
                "symbol": item.get("symbol", ""),
                "price": item.get("price"),
                "change": item.get("change"),
                "change_pct": item.get("change_pct"),
                "open": item.get("open"),
                "high": item.get("high"),
                "low": item.get("low"),
                "prev_close": item.get("prev_close"),
                "volume": item.get("volume"),
                "amount": item.get("amount"),
                "source": "neodata",
                "collected_at": self._now(),
            }
            for item in items
        ]

    def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        return []

    def finance(self, symbol: str) -> dict:
        return {}

    def fund_flow(self, symbol: str) -> dict:
        return {}

    def technical(self, symbol: str) -> dict:
        return {}
