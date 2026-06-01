import re
from datetime import datetime, timezone

import httpx
from loguru import logger

from backend.collectors.base import BaseProvider


class SinaProvider(BaseProvider):
    """通过新浪财经 HTTP 接口获取行情数据，仅实现 quote() 方法。"""

    def __init__(
        self,
        name: str,
        timeout: int = 15,
        params: dict | None = None,
        optional: bool = False,
    ) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self.quote_url: str = self.params.get("quote_url", "https://hq.sinajs.cn/list={codes}")

    @staticmethod
    def _to_sina_code(symbol: str) -> str:
        if symbol.startswith("sh") or symbol.startswith("sz") or symbol.startswith("hk") or symbol.startswith("us"):
            return symbol
        code = symbol.strip()
        if code.startswith("6"):
            return f"sh{code}"
        if code.startswith("0") or code.startswith("3"):
            return f"sz{code}"
        return f"sh{code}"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def search(self, keyword: str) -> list[dict]:
        return []

    def quote(self, symbols: list[str]) -> list[dict]:
        if not symbols:
            return []
        codes = ",".join(self._to_sina_code(s) for s in symbols)
        url = self.quote_url.replace("{codes}", codes)
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        try:
            resp = httpx.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return self._parse_quote(resp.text)
        except httpx.TimeoutException:
            logger.warning("新浪行情请求超时: url={}, timeout={}s", url, self.timeout)
            return []
        except httpx.HTTPStatusError as e:
            logger.error("新浪行情 HTTP 错误: url={}, status={}", url, e.response.status_code)
            return []
        except Exception as e:
            logger.error("新浪行情请求异常: url={}, error={}", url, e)
            return []

    def _parse_quote(self, text: str) -> list[dict]:
        results: list[dict] = []
        pattern = re.compile(r'var hq_str_(s[hz]\d+)="(.+?)"')
        for match in pattern.finditer(text):
            code = match.group(1)
            fields = match.group(2).split(",")
            if len(fields) < 32:
                logger.warning("新浪行情字段不足: code={}, fields_count={}", code, len(fields))
                continue
            results.append(self._normalize_quote(code, fields))
        return results

    def _normalize_quote(self, code: str, fields: list[str]) -> dict:
        try:
            open_price = float(fields[1]) if fields[1] else None
            prev_close = float(fields[2]) if fields[2] else None
            price = float(fields[3]) if fields[3] else None
            high = float(fields[4]) if fields[4] else None
            low = float(fields[5]) if fields[5] else None
            volume = float(fields[8]) if fields[8] else None
            amount = float(fields[9]) if fields[9] else None
        except (ValueError, IndexError):
            open_price = prev_close = price = high = low = volume = amount = None

        change = None
        change_pct = None
        if price is not None and prev_close is not None and prev_close != 0:
            change = round(price - prev_close, 4)
            change_pct = round((price - prev_close) / prev_close * 100, 2)

        amplitude = None
        if prev_close and prev_close != 0 and high is not None and low is not None:
            amplitude = round((high - low) / prev_close * 100, 2)

        return {
            "symbol": code,
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "open": open_price,
            "high": high,
            "low": low,
            "prev_close": prev_close,
            "volume": volume,
            "amount": amount,
            "amplitude": amplitude,
            "turnover_rate": None,
            "high_52w": None,
            "low_52w": None,
            "source": "sina",
            "collected_at": self._now(),
        }

    def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        return []

    def finance(self, symbol: str) -> dict:
        return {}

    def fund_flow(self, symbol: str) -> dict:
        return {}

    def technical(self, symbol: str) -> dict:
        return {}
