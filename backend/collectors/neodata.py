import asyncio
from datetime import datetime, timezone
import re

from loguru import logger

from backend.collectors.base import BaseProvider
from backend.collectors.neodata_client import NeoDataClient


class NeoDataProvider(BaseProvider):
    """NeoData 采集提供者（异步版）。

    Token 生命周期由外部 workbuddy 工具管理,本类只读不写:
    - 凭证读取顺序:本地缓存 ~/.workbuddy/.neodata_token → config.yaml.params.token → 环境变量 NEODATA_TOKEN
    - 缺失或过期时静默降级（_query 返回 None,各业务方法返回空集合 / 空 dict）,
      不会抛异常上抛,不会阻塞其他数据源。
    - 写盘操作仅由 _retry_on_auth_error 触发 clear_cache() 清掉本地坏 token,
      不会主动申请新 token。
    详见 backend/collectors/neodata_client.py::TokenManager。
    """

    def __init__(self, name: str, timeout: int = 30, params: dict | None = None, optional: bool = True) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self._endpoint: str = self.params.get("endpoint", "https://copilot.tencent.com/agenttool/v1/neodata")
        self._config_token: str | None = self.params.get("token", "") or None
        # 懒加载 NeoDataClient：底层持有 httpx.AsyncClient，
        # 延迟到首次 await 使用时再创建，避免 import 阶段阻塞。
        self._client: NeoDataClient | None = None
        # 并发信号量：限制对底层 HTTP 客户端的并发请求数，
        # 避免 QPS 限流。底层 httpx.AsyncClient 本身支持并发，但服务端有限。
        self._sem: asyncio.Semaphore = asyncio.Semaphore(5)

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
                if ":" in seg or "：" in seg:
                    sep = "：" if "：" in seg else ":"
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
            (r"营业总收入\s*[:：]?\s*([\d,]+\.?\d*)\s*亿", "营业收入"),
            (r"营业收入\s*[:：]?\s*([\d,]+\.?\d*)\s*亿", "营业收入"),
            (r"归母净利润\s*[:：]?\s*([\d,]+\.?\d*)\s*亿", "净利润"),
            (r"净利润\s*[:：]?\s*([\d,]+\.?\d*)\s*亿", "净利润"),
            (r"营收[^\d]*?[增加长涨]\s*[:：]?\s*([\-\d,]+\.?\d*)%?", "营收同比增长"),
            (r"净利润[^\d]*?[增加长涨]\s*[:：]?\s*([\-\d,]+\.?\d*)%?", "净利润同比增长"),
            (r"每股收益\s*[:：]?\s*([\d,]+\.?\d*)\s*元?", "每股收益"),
            (r"净资产收益率\s*[:：]?\s*([\d,]+\.?\d*)%?", "净资产收益率"),
            (r"ROE\s*[:：]?\s*([\d,]+\.?\d*)%?", "净资产收益率"),
            (r"资产负债率\s*[:：]?\s*([\d,]+\.?\d*)%?", "资产负债率"),
            (r"毛利率\s*[:：]?\s*([\d,]+\.?\d*)%?", "毛利率"),
            (r"净利率\s*[:：]?\s*([\d,]+\.?\d*)%?", "净利率"),
            (r"报告期\s*[:：]?\s*(\S+)", "报告期"),
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
                if content and (":" in content or "：" in content):
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
            cleaned = re.sub(r"[,%亿万元]", "", str(value))
            if not cleaned or cleaned == "-":
                return None
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Structured data methods（异步版）
    # ------------------------------------------------------------------

    async def quote(self, symbols: list[str]) -> list[dict]:
        """并发获取多个标的的最新行情（Semaphore 限流）。"""
        if not symbols:
            return []

        async def _fetch_one(symbol: str) -> dict | None:
            async with self._sem:
                info = await self._get_basic_info(symbol, f"{symbol}最新行情")
            if info is None:
                return None
            return {
                "symbol": symbol,
                "price": self._try_float(info.get("最新价格") or info.get("最新价")),
                "change": self._try_float(info.get("涨跌额")),
                "change_pct": self._try_float(info.get("当日涨跌幅") or info.get("涨跌幅")),
                "open": self._try_float(info.get("今日开盘价格") or info.get("今开")),
                "high": self._try_float(info.get("最高价") or info.get("最高")),
                "low": self._try_float(info.get("最低价") or info.get("最低")),
                "prev_close": self._try_float(info.get("昨日收盘价格") or info.get("昨收")),
                "volume": self._try_float(info.get("成交数量(手)") or info.get("成交量")),
                "amount": self._try_float(info.get("成交金额(万元)") or info.get("成交额")),
                "source": "neodata",
                "collected_at": self._now(),
            }

        results = await asyncio.gather(
            *[_fetch_one(s) for s in symbols], return_exceptions=False
        )
        return [r for r in results if r is not None]

    async def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        return []

    async def finance(self, symbol: str) -> dict[str, object]:
        query_text = f"{symbol}最新财报"
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
            "report_period": info.get("报告期"),
            "revenue": self._try_float(info.get("营业收入")),
            "revenue_yoy": self._try_float(info.get("营收同比增长")),
            "net_profit": self._try_float(info.get("净利润")),
            "net_profit_yoy": self._try_float(info.get("净利润同比增长")),
            "eps": self._try_float(info.get("每股收益")),
            "roe": self._try_float(info.get("净资产收益率")),
            "debt_ratio": self._try_float(info.get("资产负债率")),
            "gross_margin": self._try_float(info.get("毛利率")),
            "net_margin": self._try_float(info.get("净利率")),
            "source": "neodata",
            "collected_at": self._now(),
        }

    async def fund_flow(self, symbol: str) -> dict[str, object]:
        info = await self._get_basic_info(symbol, f"{symbol}资金流向")
        if info is None:
            return {}
        return {
            "main_net_inflow": self._try_float(info.get("主力净流入")),
            "net_inflow_ratio": self._try_float(info.get("净流入占比")),
            "source": "neodata",
            "collected_at": self._now(),
        }

    async def technical(self, symbol: str) -> dict[str, object]:
        return {}

    # ------------------------------------------------------------------
    # News collection（异步版）
    async def fetch_news(self, symbols: list[str]) -> list[dict]:
        """并发获取多个标的的最新新闻（Semaphore 限流）。"""
        if not symbols:
            return []

        async def _fetch_one(symbol: str) -> list[dict]:
            items: list[dict] = []
            async with self._sem:
                result = await self._query(f"{symbol}最新新闻", data_type="doc")
            if result is None:
                return items
            try:
                doc_data = result.get("data", {}).get("docData", {})
                for group in (doc_data.get("docRecall") or []):
                    for doc in (group.get("docList") or []):
                        published_at = None
                        pt = doc.get("publishTime")
                        if pt:
                            try:
                                published_at = datetime.fromtimestamp(pt, tz=timezone.utc).isoformat()
                            except (ValueError, OSError):
                                published_at = None
                        items.append({
                            "title": doc.get("title", ""),
                            "source": doc.get("source", ""),
                            "url": doc.get("url", "") or None,
                            "content": doc.get("content"),
                            "published_at": published_at,
                            "collected_at": self._now(),
                        })
            except Exception as e:
                self._log_error("NeoData fetch_news 解析异常: symbol={symbol}, error={error}", symbol=symbol, error=e)
            return items

        per_symbol = await asyncio.gather(
            *[_fetch_one(s) for s in symbols], return_exceptions=False
        )

        # 跨标的去重 URL
        all_items: list[dict] = []
        seen_urls: set[str] = set()
        for items in per_symbol:
            for item in items:
                url = item.get("url")
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                all_items.append(item)
        return all_items
