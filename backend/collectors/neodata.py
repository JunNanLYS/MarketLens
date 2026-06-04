from datetime import datetime, timezone
import re

from loguru import logger

from backend.collectors.base import BaseProvider
from backend.collectors.neodata_client import NeoDataClient


class NeoDataProvider(BaseProvider):
    """NeoData 采集提供者（异步版）。"""

    def __init__(self, name: str, timeout: int = 30, params: dict | None = None, optional: bool = True) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self._endpoint: str = self.params.get("endpoint", "https://copilot.tencent.com/agenttool/v1/neodata")
        self._config_token: str | None = self.params.get("token", "") or None
        # 懒加载 NeoDataClient：底层持有 httpx.AsyncClient，
        # 延迟到首次 await 使用时再创建，避免 import 阶段阻塞。
        self._client: NeoDataClient | None = None

    def _get_inner_client(self) -> NeoDataClient:
        """首次使用时创建 NeoDataClient，后续复用。"""
        if self._client is None:
            self._client = NeoDataClient(
                endpoint=self._endpoint,
                config_token=self._config_token,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


    def _log_error(self, msg: str, **kwargs: object) -> None:
        if self.optional:
            logger.warning(msg, **kwargs)
        else:
            logger.error(msg, **kwargs)

    async def _query(self, query_text: str, data_type: str = "all") -> dict | None:
        try:
            client = self._get_inner_client()
            return await client.query(query_text, data_type=data_type)
        except Exception as e:
            self._log_error("NeoData 查询异常: query={query}, error={error}", query=query_text, error=e)
            return None

    # ------------------------------------------------------------------
    # BaseProvider 接口实现（异步版）
    # ------------------------------------------------------------------

    async def search(self, keyword: str) -> list[dict]:
        result = await self._query(keyword)
        if result is None:
            return []
        entities: list[dict] = []
        try:
            api_data = result.get("data", {}).get("apiData", {})
            for ent in (api_data.get("entity") or []):
                code = ent.get("code", "")
                name = ent.get("name", "")
                market = ""
                if "." in code:
                    suffix = code.rsplit(".", 1)[1].upper()
                    market_map = {"HK": "hk", "US": "us", "SH": "sh", "SZ": "sz"}
                    market = market_map.get(suffix, "")
                entities.append({
                    "symbol": code,
                    "name": name,
                    "market": market,
                    "source": "neodata",
                    "collected_at": self._now(),
                })
        except Exception as e:
            self._log_error("NeoData search 解析异常: {error}", error=e)
        return entities

    # ------------------------------------------------------------------
    # Content parsing helpers（同步）
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_basic_info_content(content: str | None) -> dict[str, str]:
        result: dict[str, str] = {}
        if not content:
            return result
        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue
            segments = line.split(";")
            for seg in segments:
                seg = seg.strip()
                if not seg:
                    continue
                if ":" in seg or "\uff1a" in seg:
                    sep = "\uff1a" if "\uff1a" in seg else ":"
                    parts = seg.split(sep, 1)
                    if len(parts) == 2:
                        key = parts[0].strip().rstrip(";")
                        val = parts[1].strip().rstrip(";")
                        if key:
                            result[key] = val
        return result

    @staticmethod
    def _raw_text(result: dict | None) -> str:
        if result is None:
            return ""
        parts: list[str] = []
        api_data = result.get("data", {}).get("apiData", {})
        for recall in (api_data.get("apiRecall") or []):
            c = recall.get("content", "")
            if c:
                parts.append(c)
        return "\n".join(parts)

    def _extract_finance_metrics(self, text: str) -> dict[str, str]:
        result: dict[str, str] = {}
        patterns: list[tuple[str, str]] = [
            (r"\u8425\u4e1a\u603b\u6536\u5165\s*[:\uff1a]?\s*([\d,]+\.?\d*)\s*\u4ebf", "\u8425\u4e1a\u6536\u5165"),
            (r"\u8425\u4e1a\u6536\u5165\s*[:\uff1a]?\s*([\d,]+\.?\d*)\s*\u4ebf", "\u8425\u4e1a\u6536\u5165"),
            (r"\u5f52\u6bcd\u51c0\u5229\u6da6\s*[:\uff1a]?\s*([\d,]+\.?\d*)\s*\u4ebf", "\u51c0\u5229\u6da6"),
            (r"\u51c0\u5229\u6da6\s*[:\uff1a]?\s*([\d,]+\.?\d*)\s*\u4ebf", "\u51c0\u5229\u6da6"),
            (r"\u8425\u6536[^\d]*?[\u589e\u52a0\u957f\u6da8]\s*[:\uff1a]?\s*([\-\d,]+\.?\d*)%?", "\u8425\u6536\u540c\u6bd4\u589e\u957f"),
            (r"\u51c0\u5229\u6da6[^\d]*?[\u589e\u52a0\u957f\u6da8]\s*[:\uff1a]?\s*([\-\d,]+\.?\d*)%?", "\u51c0\u5229\u6da6\u540c\u6bd4\u589e\u957f"),
            (r"\u6bcf\u80a1\u6536\u76ca\s*[:\uff1a]?\s*([\d,]+\.?\d*)\s*\u5143?", "\u6bcf\u80a1\u6536\u76ca"),
            (r"\u51c0\u8d44\u4ea7\u6536\u76ca\u7387\s*[:\uff1a]?\s*([\d,]+\.?\d*)%?", "\u51c0\u8d44\u4ea7\u6536\u76ca\u7387"),
            (r"ROE\s*[:\uff1a]?\s*([\d,]+\.?\d*)%?", "\u51c0\u8d44\u4ea7\u6536\u76ca\u7387"),
            (r"\u8d44\u4ea7\u8d1f\u503a\u7387\s*[:\uff1a]?\s*([\d,]+\.?\d*)%?", "\u8d44\u4ea7\u8d1f\u503a\u7387"),
            (r"\u6bdb\u5229\u7387\s*[:\uff1a]?\s*([\d,]+\.?\d*)%?", "\u6bdb\u5229\u7387"),
            (r"\u51c0\u5229\u7387\s*[:\uff1a]?\s*([\d,]+\.?\d*)%?", "\u51c0\u5229\u7387"),
            (r"\u62a5\u544a\u671f\s*[:\uff1a]?\s*(\S+)", "\u62a5\u544a\u671f"),
        ]
        for pat, key in patterns:
            if key in result:
                continue
            m = re.search(pat, text)
            if m:
                result[key] = m.group(1)
        return result

    async def _get_basic_info(self, symbol: str, query_text: str, result: dict | None = None) -> dict[str, str] | None:
        if result is None:
            result = await self._query(query_text)
        if result is None:
            return None
        try:
            api_data = result.get("data", {}).get("apiData", {})
            merged: dict[str, str] = {}
            for recall in (api_data.get("apiRecall") or []):
                content = recall.get("content", "")
                if content and (":" in content or "\uff1a" in content):
                    parsed = self._parse_basic_info_content(content)
                    merged.update(parsed)
            return merged if merged else None
        except Exception as e:
            self._log_error("NeoData basic_info 解析异常: symbol={symbol}, error={error}", symbol=symbol, error=e)
        return None

    @staticmethod
    def _try_float(value: str | int | float | None) -> float | None:
        if value is None:
            return None
        try:
            cleaned = re.sub(r"[,%\u4ebf\u4e07\u5143]", "", str(value))
            if not cleaned or cleaned == "-":
                return None
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Structured data methods（异步版）
    # ------------------------------------------------------------------

    async def quote(self, symbols: list[str]) -> list[dict]:
        items: list[dict] = []
        for symbol in symbols:
            info = await self._get_basic_info(symbol, f"{symbol}\u6700\u65b0\u884c\u60c5")
            if info is None:
                continue
            items.append({
                "symbol": symbol,
                "price": self._try_float(info.get("\u6700\u65b0\u4ef7\u683c") or info.get("\u6700\u65b0\u4ef7")),
                "change": self._try_float(info.get("\u6da8\u8dcc\u989d")),
                "change_pct": self._try_float(info.get("\u5f53\u65e5\u6da8\u8dcc\u5e45") or info.get("\u6da8\u8dcc\u5e45")),
                "open": self._try_float(info.get("\u4eca\u65e5\u5f00\u76d8\u4ef7\u683c") or info.get("\u4eca\u5f00")),
                "high": self._try_float(info.get("\u6700\u9ad8\u4ef7") or info.get("\u6700\u9ad8")),
                "low": self._try_float(info.get("\u6700\u4f4e\u4ef7") or info.get("\u6700\u4f4e")),
                "prev_close": self._try_float(info.get("\u6628\u65e5\u6536\u76d8\u4ef7\u683c") or info.get("\u6628\u6536")),
                "volume": self._try_float(info.get("\u6210\u4ea4\u6570\u91cf(\u624b)") or info.get("\u6210\u4ea4\u91cf")),
                "amount": self._try_float(info.get("\u6210\u4ea4\u91d1\u989d(\u4e07\u5143)") or info.get("\u6210\u4ea4\u989d")),
                "source": "neodata",
                "collected_at": self._now(),
            })
        return items

    async def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        return []

    async def finance(self, symbol: str) -> dict[str, object]:
        query_text = f"{symbol}\u6700\u65b0\u8d22\u62a5"
        query_result = await self._query(query_text)
        if query_result is None:
            return {}
        info = await self._get_basic_info(symbol, query_text, result=query_result)
        if info is None:
            info = {}
        raw = self._raw_text(query_result)
        if raw:
            extracted = self._extract_finance_metrics(raw)
            for k, v in extracted.items():
                if v is not None and k not in info:
                    info[k] = v
        return {
            "report_period": info.get("\u62a5\u544a\u671f"),
            "revenue": self._try_float(info.get("\u8425\u4e1a\u6536\u5165")),
            "revenue_yoy": self._try_float(info.get("\u8425\u6536\u540c\u6bd4\u589e\u957f")),
            "net_profit": self._try_float(info.get("\u51c0\u5229\u6da6")),
            "net_profit_yoy": self._try_float(info.get("\u51c0\u5229\u6da6\u540c\u6bd4\u589e\u957f")),
            "eps": self._try_float(info.get("\u6bcf\u80a1\u6536\u76ca")),
            "roe": self._try_float(info.get("\u51c0\u8d44\u4ea7\u6536\u76ca\u7387")),
            "debt_ratio": self._try_float(info.get("\u8d44\u4ea7\u8d1f\u503a\u7387")),
            "gross_margin": self._try_float(info.get("\u6bdb\u5229\u7387")),
            "net_margin": self._try_float(info.get("\u51c0\u5229\u7387")),
            "source": "neodata",
            "collected_at": self._now(),
        }

    async def fund_flow(self, symbol: str) -> dict[str, object]:
        info = await self._get_basic_info(symbol, f"{symbol}\u8d44\u91d1\u6d41\u5411")
        if info is None:
            return {}
        return {
            "main_net_inflow": self._try_float(info.get("\u4e3b\u529b\u51c0\u6d41\u5165")),
            "net_inflow_ratio": self._try_float(info.get("\u51c0\u6d41\u5165\u5360\u6bd4")),
            "source": "neodata",
            "collected_at": self._now(),
        }

    async def technical(self, symbol: str) -> dict[str, object]:
        return {}

    # ------------------------------------------------------------------
    # News collection（异步版）
    async def fetch_news(self, symbols: list[str]) -> list[dict]:
        if not symbols:
            return []
        all_items: list[dict] = []
        seen_urls: set[str] = set()
        for symbol in symbols:
            result = await self._query(f"{symbol}\u6700\u65b0\u65b0\u95fb", data_type="doc")
            if result is None:
                continue
            try:
                doc_data = result.get("data", {}).get("docData", {})
                for group in (doc_data.get("docRecall") or []):
                    for doc in (group.get("docList") or []):
                        url = doc.get("url", "")
                        if url and url in seen_urls:
                            continue
                        if url:
                            seen_urls.add(url)
                        published_at = None
                        pt = doc.get("publishTime")
                        if pt:
                            try:
                                published_at = datetime.fromtimestamp(pt, tz=timezone.utc).isoformat()
                            except (ValueError, OSError):
                                published_at = None
                        all_items.append({
                            "title": doc.get("title", ""),
                            "source": doc.get("source", ""),
                            "url": url or None,
                            "content": doc.get("content"),
                            "published_at": published_at,
                            "collected_at": self._now(),
                        })
            except Exception as e:
                self._log_error("NeoData fetch_news 解析异常: symbol={symbol}, error={error}", symbol=symbol, error=e)
        return all_items
