from datetime import datetime, timezone
import re

from loguru import logger

from backend.collectors.base import BaseProvider
from backend.collectors.neodata_client import NeoDataClient


class NeoDataProvider(BaseProvider):

    def __init__(self, name: str, timeout: int = 30, params: dict | None = None, optional: bool = True) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self._endpoint: str = self.params.get("endpoint", "https://copilot.tencent.com/agenttool/v1/neodata")
        self._config_token: str | None = self.params.get("token", "") or None
        self._client = NeoDataClient(
            endpoint=self._endpoint,
            config_token=self._config_token,
            timeout=timeout,
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _log_error(self, msg: str, **kwargs: object) -> None:
        if self.optional:
            logger.warning(msg, **kwargs)
        else:
            logger.error(msg, **kwargs)

    def _query(self, query_text: str, data_type: str = "all") -> dict | None:
        try:
            return self._client.query(query_text, data_type=data_type)
        except Exception as e:
            self._log_error("NeoData \u67e5\u8be2\u5f02\u5e38: query={query}, error={error}", query=query_text, error=e)
            return None

    # ------------------------------------------------------------------
    # BaseProvider \u63a5\u53e3\u5b9e\u73b0
    # ------------------------------------------------------------------

    def search(self, keyword: str) -> list[dict]:
        result = self._query(keyword)
        if result is None:
            return []
        entities: list[dict] = []
        try:
            api_data = result.get("data", {}).get("apiData", {})
            for ent in (api_data.get("entity") or []):
                code = ent.get("name", "")
                name = ent.get("code", "")
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
            self._log_error("NeoData search \u89e3\u6790\u5f02\u5e38: {error}", error=e)
        return entities

    # ------------------------------------------------------------------
    # Content parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_basic_info_content(content: str | None) -> dict[str, str]:
        """\u89e3\u6790\u884c\u60c5\u6570\u636e\u5185\u5bb9\u3002
        NeoData API \u8fd4\u56de\u7684\u884c\u60c5\u6570\u636e\u4e3a\u4e00\u884c\u5185\u7528\u5206\u53f7\u5206\u9694\u7684 key:value \u683c\u5f0f\u3002
        """
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
        """\u63d0\u53d6 apiRecall \u4e2d\u6240\u6709 content \u7684\u7eaf\u6587\u672c\u62fc\u63a5\u3002"""
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
        """\u4ece\u81ea\u7136\u8bed\u8a00\u8d22\u62a5\u6bb5\u843d\u4e2d\u63d0\u53d6\u5173\u952e\u8d22\u52a1\u6307\u6807\u3002
        NeoData \u8d22\u62a5\u6570\u636e\u4ee5\u6bb5\u843d\u5f62\u5f0f\u8fd4\u56de\uff0c\u4e0d\u9002\u7528 key:value \u89e3\u6790\u3002
        """
        result: dict[str, str] = {}
        patterns: list[tuple[str, str]] = [
            (r"\u8425\u4e1a\u603b\u6536\u5165\s*[:\uff1a]?\s*([\d,]+\.?\d*)\s*\u4ebf", "\u8425\u4e1a\u6536\u5165"),
            (r"\u8425\u4e1a\u6536\u5165\s*[:\uff1a]?\s*([\d,]+\.?\d*)\s*\u4ebf", "\u8425\u4e1a\u6536\u5165"),
            (r"\u5f52\u6bcd\u51c0\u5229\u6da6\s*[:\uff1a]?\s*([\d,]+\.?\d*)\s*\u4ebf", "\u51c0\u5229\u6da6"),
            (r"\u51c0\u5229\u6da6\s*[:\uff1a]?\s*([\d,]+\.?\d*)\s*\u4ebf", "\u51c0\u5229\u6da6"),
            (r"\u5f52\u6bcd\u51c0\u5229\u6da6[^\d]*?[\u589e\u52a0\u957f\u6da8]\s*[:\uff1a]?\s*([\-\d,]+\.?\d*)%?", "\u51c0\u5229\u6da6\u540c\u6bd4\u589e\u957f"),
            (r"\u51c0\u5229\u6da6[^\d]*?[\u589e\u52a0\u957f\u6da8]\s*[:\uff1a]?\s*([\-\d,]+\.?\d*)%?", "\u51c0\u5229\u6da6\u540c\u6bd4\u589e\u957f"),
            (r"\u8425\u6536[^\d]*?[\u589e\u52a0\u957f\u6da8]\s*[:\uff1a]?\s*([\-\d,]+\.?\d*)%?", "\u8425\u6536\u540c\u6bd4\u589e\u957f"),
            (r"\u6bcf\u80a1\u6536\u76ca\s*[:\uff1a]?\s*([\d,]+\.?\d*)\s*\u5143?", "\u6bcf\u80a1\u6536\u76ca"),
            (r"\u51c0\u8d44\u4ea7\u6536\u76ca\u7387\s*[:\uff1a]?\s*([\d,]+\.?\d*)%?", "\u51c0\u8d44\u4ea7\u6536\u76ca\u7387"),
            (r"\u8d44\u4ea7\u8d1f\u503a\u7387\s*[:\uff1a]?\s*([\d,]+\.?\d*)%?", "\u8d44\u4ea7\u8d1f\u503a\u7387"),
            (r"\u6bdb\u5229\u7387\s*[:\uff1a]?\s*([\d,]+\.?\d*)%?", "\u6bdb\u5229\u7387"),
            (r"\u51c0\u5229\u7387\s*[:\uff1a]?\s*([\d,]+\.?\d*)%?", "\u51c0\u5229\u7387"),
            (r"\u62a5\u544a\u671f\s*[:\uff1a]?\s*(\S+)", "\u62a5\u544a\u671f"),
            (r"\u8425\u6536[^\d]*?[\u589e\u52a0\u957f\u6da8]\s*[:\uff1a]?\s*([\-\d,]+\.?\d*)%?", "\u8425\u6536\u540c\u6bd4\u589e\u957f"),
            (r"ROE\s*[:\uff1a]?\s*([\d,]+\.?\d*)%?", "\u51c0\u8d44\u4ea7\u6536\u76ca\u7387"),
            (r"\u8d44\u4ea7\u56de\u62a5\u7387ROA\s*[:\uff1a]?\s*([\d,]+\.?\d*)%?", "\u51c0\u8d44\u4ea7\u6536\u76ca\u7387"),
            (r"\u51c0\u8d44\u4ea7\u6536\u76ca\u7387[^\d]*?([\d,]+\.?\d*)%?", "\u51c0\u8d44\u4ea7\u6536\u76ca\u7387"),
        ]
        for pat, key in patterns:
            if key in result:
                continue
            m = re.search(pat, text)
            if m:
                result[key] = m.group(1)
        return result

    def _get_basic_info(self, symbol: str, query_text: str) -> dict[str, str] | None:
        """\u83b7\u53d6\u7ed3\u6784\u5316\u6570\u636e\u5757\u3002
        NeoData API \u8fd4\u56de\u7684 apiRecall type \u4e3a\u4e2d\u6587\u540d\u79f0\uff0c\u4e0d\u4f7f\u7528\u56fa\u5b9a\u7684 "basic_info" \u6807\u8bc6\u3002
        \u56e0\u6b64\u5408\u5e76\u6240\u6709\u5305\u542b\u5192\u53f7\u5206\u9694\u5185\u5bb9\u7684 recall\uff0c\u4e0d\u4f9d\u8d56 type \u5b57\u6bb5\u5339\u914d\u3002
        """
        result = self._query(query_text)
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
            self._log_error(
                "NeoData basic_info \u89e3\u6790\u5f02\u5e38: symbol={symbol}, error={error}",
                symbol=symbol, error=e,
            )
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
    # Structured data methods
    # ------------------------------------------------------------------

    def quote(self, symbols: list[str]) -> list[dict]:
        """\u83b7\u53d6\u5b9e\u65f6\u884c\u60c5\u3002
        NeoData API \u8fd4\u56de\u7684 key \u540d\u4e0e\u5185\u90e8\u547d\u540d\u7ea6\u5b9a\u4e0d\u5b8c\u5168\u4e00\u81f4\uff0c\u9700\u591a\u5019\u9009\u6620\u5c04\u3002
        """
        items: list[dict] = []
        for symbol in symbols:
            info = self._get_basic_info(symbol, f"{symbol}\u6700\u65b0\u884c\u60c5")
            if info is None:
                continue
            items.append({
                "symbol": symbol,
                "price": self._try_float(
                    info.get("\u6700\u65b0\u4ef7\u683c") or info.get("\u6700\u65b0\u4ef7")
                ),
                "change": self._try_float(info.get("\u6da8\u8dcc\u989d")),
                "change_pct": self._try_float(
                    info.get("\u5f53\u65e5\u6da8\u8dcc\u5e45") or info.get("\u6da8\u8dcc\u5e45")
                ),
                "open": self._try_float(
                    info.get("\u4eca\u65e5\u5f00\u76d8\u4ef7\u683c") or info.get("\u4eca\u5f00")
                ),
                "high": self._try_float(
                    info.get("\u6700\u9ad8\u4ef7") or info.get("\u6700\u9ad8")
                ),
                "low": self._try_float(
                    info.get("\u6700\u4f4e\u4ef7") or info.get("\u6700\u4f4e")
                ),
                "prev_close": self._try_float(
                    info.get("\u6628\u65e5\u6536\u76d8\u4ef7\u683c") or info.get("\u6628\u6536")
                ),
                "volume": self._try_float(
                    info.get("\u6210\u4ea4\u6570\u91cf(\u624b)") or info.get("\u6210\u4ea4\u91cf")
                ),
                "amount": self._try_float(
                    info.get("\u6210\u4ea4\u91d1\u989d(\u4e07\u5143)") or info.get("\u6210\u4ea4\u989d")
                ),
                "source": "neodata",
                "collected_at": self._now(),
            })
        return items

    def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        return []

    def finance(self, symbol: str) -> dict[str, object]:
        """\u83b7\u53d6\u8d22\u52a1\u6570\u636e\u3002
        \u4f18\u5148\u4ece key:value \u89e3\u6790\u7ed3\u679c\u4e2d\u63d0\u53d6\uff0c\u8f85\u4ee5\u6b63\u5219\u4ece\u6bb5\u843d\u6587\u672c\u4e2d\u8865\u5145\u3002
        """
        query_text = f"{symbol}\u6700\u65b0\u8d22\u62a5"
        query_result = self._query(query_text)
        if query_result is None:
            return {}
        info = self._get_basic_info(symbol, query_text)
        if info is None:
            info = {}
        # \u8865\u5145\uff1a\u7528 regex \u4ece\u6bb5\u843d\u6587\u672c\u4e2d\u63d0\u53d6\u6307\u6807
        raw = self._raw_text(self._query(query_text))
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

    def fund_flow(self, symbol: str) -> dict[str, object]:
        info = self._get_basic_info(symbol, f"{symbol}\u8d44\u91d1\u6d41\u5411")
        if info is None:
            return {}
        return {
            "main_net_inflow": self._try_float(info.get("\u4e3b\u529b\u51c0\u6d41\u5165")),
            "net_inflow_ratio": self._try_float(info.get("\u51c0\u6d41\u5165\u5360\u6bd4")),
            "source": "neodata",
            "collected_at": self._now(),
        }

    def technical(self, symbol: str) -> dict[str, object]:
        return {}

    # ------------------------------------------------------------------
    # News collection
    # ------------------------------------------------------------------

    def _get_tracked_symbols(self) -> list[str]:
        try:
            from backend.storage.database import get_db
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT symbol, name FROM tracked_assets WHERE enabled = 1"
                ).fetchall()
            return [f"{r['name']}({r['symbol']})" for r in rows]
        except Exception as e:
            self._log_error("NeoData \u83b7\u53d6\u8ffd\u8e2a\u6807\u7684\u5931\u8d25: {error}", error=e)
            return []

    def fetch_news(self, symbols: list[str] | None = None) -> list[dict]:
        if symbols is None:
            symbols = self._get_tracked_symbols()
        if not symbols:
            return []
        all_items: list[dict] = []
        seen_urls: set[str] = set()
        for symbol in symbols:
            result = self._query(f"{symbol}\u6700\u65b0\u65b0\u95fb", data_type="doc")
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
                self._log_error(
                    "NeoData fetch_news \u89e3\u6790\u5f02\u5e38: symbol={symbol}, error={error}",
                    symbol=symbol, error=e,
                )
        return all_items
