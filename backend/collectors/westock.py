import json
import subprocess
from datetime import datetime, timezone

from loguru import logger

from backend.collectors.base import BaseProvider


class WeStockProvider(BaseProvider):
    """通过 westock-data-clawhub CLI 获取结构化金融数据。"""

    def __init__(
        self,
        name: str,
        timeout: int = 30,
        params: dict | None = None,
        optional: bool = False,
    ) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self.command: str = self.params.get("command", "npx -y westock-data-clawhub@1.0.4")

    def _run_cli(self, args: str) -> list[dict] | dict | None:
        cmd_parts = self.command.split() + args.split()
        try:
            result = subprocess.run(
                cmd_parts,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True,
            )
            data: list[dict] | dict = json.loads(result.stdout)
            return data
        except subprocess.TimeoutExpired:
            logger.warning("WeStock CLI 超时: cmd={}, timeout={}s", cmd_parts, self.timeout)
            return None
        except subprocess.CalledProcessError as e:
            logger.error("WeStock CLI 执行失败: cmd={}, rc={}, stderr={}", cmd_parts, e.returncode, e.stderr)
            return None
        except json.JSONDecodeError as e:
            logger.error("WeStock CLI 返回非 JSON: cmd={}, error={}", cmd_parts, e)
            return None
        except Exception as e:
            logger.error("WeStock CLI 未知异常: cmd={}, error={}", cmd_parts, e)
            return None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def search(self, keyword: str) -> list[dict]:
        data = self._run_cli(f"search --keyword {keyword}")
        if data is None:
            return []
        if isinstance(data, list):
            return data
        return [data]

    def quote(self, symbols: list[str]) -> list[dict]:
        symbols_str = ",".join(symbols)
        data = self._run_cli(f"quote --symbols {symbols_str}")
        if data is None:
            return []
        items = data if isinstance(data, list) else [data]
        return [self._normalize_quote(item) for item in items]

    def _normalize_quote(self, raw: dict) -> dict:
        return {
            "symbol": raw.get("symbol", ""),
            "price": raw.get("price"),
            "change": raw.get("change"),
            "change_pct": raw.get("change_pct"),
            "open": raw.get("open"),
            "high": raw.get("high"),
            "low": raw.get("low"),
            "prev_close": raw.get("prev_close"),
            "volume": raw.get("volume"),
            "amount": raw.get("amount"),
            "amplitude": raw.get("amplitude"),
            "turnover_rate": raw.get("turnover_rate"),
            "high_52w": raw.get("high_52w"),
            "low_52w": raw.get("low_52w"),
            "source": "westock",
            "collected_at": self._now(),
        }

    def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        data = self._run_cli(f"kline --symbol {symbol} --period {period}")
        if data is None:
            return []
        items = data if isinstance(data, list) else [data]
        return [self._normalize_kline(item) for item in items]

    def _normalize_kline(self, raw: dict) -> dict:
        return {
            "symbol": raw.get("symbol", ""),
            "date": raw.get("date"),
            "open": raw.get("open"),
            "high": raw.get("high"),
            "low": raw.get("low"),
            "close": raw.get("close"),
            "volume": raw.get("volume"),
            "amount": raw.get("amount"),
            "source": "westock",
            "collected_at": self._now(),
        }

    def finance(self, symbol: str) -> dict:
        data = self._run_cli(f"finance --symbol {symbol}")
        if data is None:
            return {}
        if isinstance(data, list):
            data = data[0] if data else {}
        return self._normalize_finance(data)

    def _normalize_finance(self, raw: dict) -> dict:
        return {
            "symbol": raw.get("symbol", ""),
            "report_date": raw.get("report_date"),
            "revenue": raw.get("revenue"),
            "net_profit": raw.get("net_profit"),
            "eps": raw.get("eps"),
            "period": raw.get("period"),
            "source": "westock",
            "collected_at": self._now(),
        }

    def fund_flow(self, symbol: str) -> dict:
        data = self._run_cli(f"fund-flow --symbol {symbol}")
        if data is None:
            return {}
        if isinstance(data, list):
            data = data[0] if data else {}
        return self._normalize_fund_flow(data)

    def _normalize_fund_flow(self, raw: dict) -> dict:
        return {
            "symbol": raw.get("symbol", ""),
            "date": raw.get("date"),
            "main_inflow": raw.get("main_inflow"),
            "main_outflow": raw.get("main_outflow"),
            "net_flow": raw.get("net_flow"),
            "source": "westock",
            "collected_at": self._now(),
        }

    def technical(self, symbol: str) -> dict:
        data = self._run_cli(f"technical --symbol {symbol}")
        if data is None:
            return {}
        if isinstance(data, list):
            data = data[0] if data else {}
        return self._normalize_technical(data)

    def _normalize_technical(self, raw: dict) -> dict:
        return {
            "symbol": raw.get("symbol", ""),
            "date": raw.get("date"),
            "ma5": raw.get("ma5"),
            "ma20": raw.get("ma20"),
            "macd": raw.get("macd"),
            "rsi": raw.get("rsi"),
            "boll_upper": raw.get("boll_upper"),
            "boll_lower": raw.get("boll_lower"),
            "source": "westock",
            "collected_at": self._now(),
        }
