import re
import json
from datetime import datetime, timezone

import httpx
from loguru import logger

from backend.collectors.base import BaseProvider


class SinaProvider(BaseProvider):
    """通过新浪财经 HTTP 接口获取行情、K线、财务、资金流向数据（异步版）。"""

    def __init__(
        self,
        name: str,
        timeout: int = 15,
        params: dict | None = None,
        optional: bool = False,
    ) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self.quote_url: str = self.params.get("quote_url", "https://hq.sinajs.cn/list={codes}")
        # 懒加载 httpx.AsyncClient：见 rss.py 同类注释
        self._client: httpx.AsyncClient | None = None
        self._client_headers: dict[str, str] = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """首次使用时创建 httpx 客户端，后续复用。"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                headers=self._client_headers,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _to_sina_code(symbol: str) -> str:
        if any(symbol.startswith(p) for p in ("sh", "sz", "bj", "hk", "us", "hf", "nf", "gb")):
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

    @staticmethod
    def _strip_code_for_finance(sina_code: str) -> str | None:
        """获取纯数字代码（去掉 sh/sz 前缀），用于财务/资金流向 API。"""
        if sina_code.startswith("sh") or sina_code.startswith("sz"):
            return sina_code[2:]
        if sina_code.isdigit() and len(sina_code) == 6:
            return sina_code
        return None

    @staticmethod
    def _market_prefix(sina_code: str) -> str:
        """返回市场前缀 sh/sz/bj/gb。"""
        if sina_code.startswith("sh") or sina_code.startswith("sz"):
            return sina_code[:2]
        if sina_code.startswith("bj"):
            return "bj"
        if sina_code.startswith("gb"):
            return "gb"
        code = sina_code.strip()
        if code.startswith("6"):
            return "sh"
        return "sz"

    @staticmethod
    def _safe_float(value: object) -> float | None:
        """安全转为 float，支持逗号分隔的数字字符串。"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = re.sub(r"[,\s]", "", str(value))
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Provider 接口实现（异步版）
    # ------------------------------------------------------------------

    async def search(self, keyword: str) -> list[dict]:
        return []

    async def quote(self, symbols: list[str]) -> list[dict]:
        if not symbols:
            return []
        codes = ",".join(self._to_sina_code(s) for s in symbols)
        url = self.quote_url.replace("{codes}", codes)
        try:
            client = await self._get_client()
            resp = await client.get(url)
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
        # 行情代码前缀集合需与 _to_sina_code 支持的范围保持一致：
        # sh/sz/bj 沪深京 A 股、hk 港股、us 美股、hf/nf 期货/指数等
        pattern = re.compile(r"var hq_str_((?:s[hz]|bj|hk|us|hf|nf|gb)\w*)=\"(.+?)\"")
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

    async def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        """通过新浪财经 JSON API 获取日K线数据。

        API: CN_MarketData.getKLineData，仅支持 A 股。
        """
        sina_code = self._to_sina_code(symbol)
        if sina_code.startswith("hk") or sina_code.startswith("us"):
            return []

        scale_map: dict[str, int] = {"daily": 240, "weekly": 1200, "monthly": 7200}
        scale = scale_map.get(period, 240)

        url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
        params: dict[str, str | int] = {
            "symbol": sina_code, "scale": scale, "ma": "no", "datalen": 60,
        }

        try:
            client = await self._get_client()
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list) or not data:
                logger.warning("新浪K线返回非列表或空数据: symbol={}", symbol)
                return []
            return [self._normalize_kline(symbol, item) for item in data]
        except httpx.TimeoutException:
            logger.warning("新浪K线请求超时: symbol={}, timeout={}s", symbol, self.timeout)
            return []
        except httpx.HTTPStatusError as e:
            logger.error("新浪K线 HTTP 错误: symbol={}, status={}", symbol, e.response.status_code)
            return []
        except Exception as e:
            logger.error("新浪K线请求异常: symbol={}, error={}", symbol, e)
            return []

    async def finance(self, symbol: str) -> dict:
        """通过新浪财务摘要页面获取关键财务指标。

        抓取 vFD_FinanceSummary 页面，用正则提取：报告期/营收/净利润/EPS/ROE。
        仅支持 A 股。
        """
        sina_code = self._to_sina_code(symbol)
        pure_code = self._strip_code_for_finance(sina_code)
        if pure_code is None:
            return {}

        url = (
            f"https://vip.stock.finance.sina.com.cn/corp/go.php/"
            f"vFD_FinanceSummary/stockid/{pure_code}/displaytype/4/"
        )

        try:
            client = await self._get_client()
            resp = await client.get(url)
            resp.raise_for_status()
            return self._parse_finance_html(symbol, resp.text)
        except httpx.TimeoutException:
            logger.warning("新浪财务请求超时: symbol={}, timeout={}s", symbol, self.timeout)
            return {}
        except httpx.HTTPStatusError as e:
            logger.error("新浪财务 HTTP 错误: symbol={}, status={}", symbol, e.response.status_code)
            return {}
        except Exception as e:
            logger.error("新浪财务请求异常: symbol={}, error={}", symbol, e)
            return {}

    async def fund_flow(self, symbol: str) -> dict:
        """通过新浪资金流向 API 获取主力资金数据。

        API: MoneyFlow.ssc_qzzh_js，仅支持 A 股。
        """
        sina_code = self._to_sina_code(symbol)
        pure_code = self._strip_code_for_finance(sina_code)
        if pure_code is None:
            return {}

        prefix = self._market_prefix(sina_code)
        url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssc_qzzh_js"
        params: dict[str, str] = {"daima": f"{prefix}{pure_code}"}

        try:
            client = await self._get_client()
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            text = resp.text.strip()
            if not text:
                return {}
            return self._parse_fund_flow(symbol, text)
        except httpx.TimeoutException:
            logger.warning("新浪资金流向请求超时: symbol={}, timeout={}s", symbol, self.timeout)
            return {}
        except httpx.HTTPStatusError as e:
            logger.error("新浪资金流向 HTTP 错误: symbol={}, status={}", symbol, e.response.status_code)
            return {}
        except Exception as e:
            logger.error("新浪资金流向请求异常: symbol={}, error={}", symbol, e)
            return {}

    async def technical(self, symbol: str) -> dict:
        """技术指标不在新浪直接获取，由 EvidenceBuilder 从 K 线数据计算。"""
        return {}

    # ------------------------------------------------------------------
    # 数据标准化（同步）
    # ------------------------------------------------------------------

    def _normalize_kline(self, symbol: str, raw: dict) -> dict:
        return {
            "symbol": symbol,
            "date": raw.get("day", ""),
            "open": self._safe_float(raw.get("open")),
            "high": self._safe_float(raw.get("high")),
            "low": self._safe_float(raw.get("low")),
            "close": self._safe_float(raw.get("close")),
            "volume": self._safe_float(raw.get("volume")),
            "change_pct": None,
            "source": "sina",
            "collected_at": self._now(),
        }

    def _parse_finance_html(self, symbol: str, html: str) -> dict:
        """从新浪财务摘要 HTML 中提取关键指标。"""
        report_period: str | None = None
        period_m = re.search(r"报告期[：:]\s*(\d{4}-\d{2}-\d{2})", html)
        if period_m:
            report_period = period_m.group(1)

        revenue: float | None = None
        for pat in [r"营业收入[^<]*?(\d[\d,]*\.?\d*)", r"营业总收入[^<]*?(\d[\d,]*\.?\d*)"]:
            m = re.search(pat, html)
            if m:
                revenue = float(m.group(1).replace(",", "")) * 10000  # 万元 → 元
                break

        net_profit: float | None = None
        np_m = re.search(r"净利润[^<]*?(\d[\d,]*\.?\d*)", html)
        if np_m:
            net_profit = float(np_m.group(1).replace(",", "")) * 10000

        eps: float | None = None
        eps_m = re.search(r"每股收益[^<]*?(-?[\d,]+\.?\d*)", html)
        if eps_m:
            eps = float(eps_m.group(1).replace(",", ""))

        roe: float | None = None
        roe_m = re.search(r"净资产收益率[^<]*?(-?[\d,]+\.?\d*)", html)
        if roe_m:
            roe = float(roe_m.group(1).replace(",", ""))

        return {
            "symbol": symbol,
            "report_period": report_period,
            "revenue": revenue,
            "revenue_yoy": None,
            "net_profit": net_profit,
            "net_profit_yoy": None,
            "eps": eps,
            "roe": roe,
            "debt_ratio": None,
            "gross_margin": None,
            "net_margin": None,
            "source": "sina",
            "collected_at": self._now(),
        }

    def _parse_fund_flow(self, symbol: str, text: str) -> dict:
        """解析新浪资金流向 JSON/JSONP 响应，提取最新一条。"""
        # 移除可能的 JSONP 包装（如 callback(...)）
        json_text = text
        if not text.startswith("[") and not text.startswith("{"):
            m = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
            if m:
                json_text = m.group(0)

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            logger.warning("新浪资金流向 JSON 解析失败: symbol={}", symbol)
            return {}

        latest: dict = (
            data[0] if isinstance(data, list) and data
            else data if isinstance(data, dict)
            else {}
        )
        if not latest:
            return {}

        flow_date = latest.get("date") or latest.get("day") or ""

        return {
            "symbol": symbol,
            "date": str(flow_date),
            "main_net_inflow": self._safe_float(
                latest.get("main_net_inflow") or latest.get("net_amount")
            ),
            "super_large_net_inflow": self._safe_float(latest.get("superlarge_net")),
            "large_net_inflow": self._safe_float(latest.get("large_net")),
            "medium_net_inflow": self._safe_float(latest.get("medium_net")),
            "small_net_inflow": self._safe_float(latest.get("small_net")),
            "net_inflow_ratio": self._safe_float(latest.get("net_ratio")),
            "source": "sina",
            "collected_at": self._now(),
        }