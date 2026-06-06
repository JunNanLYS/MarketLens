import asyncio
import re
import shlex
import shutil
import subprocess
from datetime import datetime

from loguru import logger

from backend.collectors.base import BaseProvider

_PERIOD_MAP: dict[str, str] = {
    "daily": "day",
    "weekly": "week",
    "monthly": "month",
}

_A_SHARE_PREFIXES: tuple[str, ...] = ("sh", "sz", "bj")

# 行情并发采集上限：避免对下游 CLI 同时发起过多请求
_QUOTE_CONCURRENCY: int = 5


def _parse_markdown_tables(text: str) -> list[list[dict[str, str]]]:
    tables: list[list[dict[str, str]]] = []
    lines = text.split("\n")
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()
        if not line.startswith("|") or _is_separator(line):
            i += 1
            continue
        header = [h.strip() for h in line.split("|")[1:-1]]
        if not header:
            i += 1
            continue
        if i + 1 < n and _is_separator(lines[i + 1].strip()):
            i += 2
            rows: list[dict[str, str]] = []
            while i < n:
                row_line = lines[i].strip()
                if not row_line.startswith("|"):
                    break
                cells = [c.strip() for c in row_line.split("|")[1:-1]]
                if len(cells) != len(header):
                    break
                rows.append(dict(zip(header, cells)))
                i += 1
            if rows:
                tables.append(rows)
            continue
        i += 1
    return tables


def _is_separator(line: str) -> bool:
    return bool(re.match(r"^\|[\s\-:|]+\|$", line))


def _detect_error(text: str) -> str | None:
    if not text.strip():
        return "CLI 返回空输出"
    patterns: list[tuple[str, str]] = [
        (r"数据为空", "未找到匹配数据"),
        (r"命令\s+\"[^\"]+\"\s+在当前渠道不可用", "该命令在当前渠道不可用"),
        (r"执行失败\s*\[(\w*\d*)\]\s*[:：]\s*", ""),
        (r"查询\S*失败\s*[:：]\s*", ""),
    ]
    for pat, _tmpl in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(0).strip()
    return None


def _try_number(val: str) -> str | int | float:
    if not val or not val.strip():
        return val
    s = val.strip()
    if "," in s:
        s = s.replace(",", "")
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return val


# westock CLI 重试常量：SKILL_006 是冷启动失败，TimeoutExpired 同理
_MAX_RETRIES: int = 2
_RETRY_BACKOFF: float = 0.5


class WeStockProvider(BaseProvider):

    def __init__(
        self,
        name: str,
        timeout: int = 30,
        params: dict | None = None,
        optional: bool = False,
    ) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self.command: str = self.params.get("command", "npx -y westock-data-clawhub@1.0.4")

    async def _run_cli(self, args: str) -> tuple[list[list[dict[str, str]]], str | None]:
        # 使用 shlex 解析 self.command，正确处理带引号/空格的复杂命令
        cmd_parts = shlex.split(self.command) + args.split()
        exe = shutil.which(cmd_parts[0])
        if exe:
            cmd_parts[0] = exe

        # SKILL_006 是 westock CLI 的冷启动失败——首次调用偶发返回，
        # 重试 1-2 次即恢复。TimeoutExpired 同理（CLI 冷启动慢）。
        # 其它错误（参数错 / 数据源无数据）立即返回，避免无谓重试。
        last_err: str | None = None
        for attempt in range(_MAX_RETRIES + 1):
            # 通过 subprocess.run（模块级引用，便于测试 mock）调用 CLI，
            # 并用 asyncio.to_thread 避免阻塞事件循环
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    cmd_parts,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
            except subprocess.TimeoutExpired:
                last_err = f"CLI 超时 ({self.timeout}s)"
                logger.warning(
                    "WeStock CLI 超时 [attempt {}/{}]: cmd={}",
                    attempt + 1, _MAX_RETRIES + 1, cmd_parts,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF * (attempt + 1))
                    continue
                return [], last_err
            except Exception as e:
                # 非超时/非 SKILL_006 错误，立即返回，不重试
                logger.error("WeStock CLI 异常: cmd={}, error={}", cmd_parts, e)
                return [], str(e)

            stdout = proc.stdout or ""
            stderr = proc.stderr or ""

            error = _detect_error(stdout)
            if error:
                last_err = error
                # 仅 SKILL_006 重试（冷启动缓解），其它业务错误立即返回
                is_skill_006 = "SKILL_006" in error
                if is_skill_006 and attempt < _MAX_RETRIES:
                    logger.warning(
                        "WeStock CLI 冷启动失败 [attempt {}/{}]: cmd={}, error={}",
                        attempt + 1, _MAX_RETRIES + 1, cmd_parts, error,
                    )
                    await asyncio.sleep(_RETRY_BACKOFF * (attempt + 1))
                    continue
                logger.warning("WeStock CLI 业务错误: cmd={}, error={}", cmd_parts, error)
                return [], error

            if proc.returncode != 0:
                # 非零退出码立即返回，不重试（重试也无法修复 CLI bug）
                msg = stderr.strip() or stdout.strip()[:200] or f"exit code {proc.returncode}"
                logger.warning("WeStock CLI 非零退出: rc={}, msg={}", proc.returncode, msg)
                return [], msg

            tables = _parse_markdown_tables(stdout)
            if not tables:
                logger.info("WeStock CLI 返回无表格数据: cmd={}", cmd_parts)

            return tables, None

        # 理论上不可达（循环内已 return），但保留防御
        return [], last_err

    async def search(self, keyword: str) -> list[dict]:
        tables, err = await self._run_cli(f"search {keyword}")
        if err or not tables:
            return []
        rows = tables[0]
        return [
            {"code": r.get("code", ""), "name": r.get("name", ""), "type": r.get("type", "")}
            for r in rows
        ]

    async def quote(self, symbols: list[str]) -> list[dict]:
        if not symbols:
            return []
        semaphore = asyncio.Semaphore(_QUOTE_CONCURRENCY)

        async def _fetch_one(sym: str) -> list[dict]:
            async with semaphore:
                tables, err = await self._run_cli(f"kline {sym} --period day --limit 1")
                if err or not tables:
                    return []
                return [self._normalize_quote(row, sym) for row in tables[0]]

        nested = await asyncio.gather(*(_fetch_one(s) for s in symbols))
        results: list[dict] = []
        for chunk in nested:
            results.extend(chunk)
        return results

    async def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        cli_period = _PERIOD_MAP.get(period, "day")
        tables, err = await self._run_cli(f"kline {symbol} --period {cli_period} --limit 60")
        if err or not tables:
            return []
        results: list[dict] = []
        for row in tables[0]:
            results.append(self._normalize_kline(row, symbol))
        return results

    async def finance(self, symbol: str) -> dict:
        tables, err = await self._run_cli(f"finance {symbol}")
        if err or not tables:
            return {}
        return self._normalize_finance(tables, symbol)

    async def fund_flow(self, symbol: str) -> dict:
        fund_cmd = self._fund_flow_cmd(symbol)
        tables, err = await self._run_cli(f"{fund_cmd} {symbol}")
        if err or not tables:
            return {}
        row = tables[0][0] if tables[0] else {}
        return self._normalize_fund_flow(row, symbol)

    async def technical(self, symbol: str) -> dict:
        tables, err = await self._run_cli(f"technical {symbol}")
        if err or not tables:
            return {}
        row = tables[0][0] if tables[0] else {}
        return self._normalize_technical(row, symbol)

    async def fetch_news(self, symbols: list[str] | None = None) -> list[dict]:
        tables, err = await self._run_cli("hot news --limit 50")
        if err or not tables:
            return []
        items: list[dict] = []
        for row in tables[0]:
            ts = _try_number(row.get("publish_time", ""))
            published_at = None
            if isinstance(ts, (int, float)):
                from datetime import timezone as _tz
                try:
                    published_at = datetime.fromtimestamp(float(ts), tz=_tz.utc).isoformat()
                except (ValueError, OSError):
                    pass
            news_id = row.get("news_id", "")
            rank_val = _try_number(row.get("rank", ""))
            rank = int(rank_val) if isinstance(rank_val, (int, float)) else 99
            if rank <= 5:
                importance = "high"
            elif rank <= 15:
                importance = "normal"
            else:
                importance = "low"
            items.append({
                "title": row.get("news_title", ""),
                "source": row.get("source", ""),
                "url": f"wehot://{news_id}" if news_id else None,
                "content": None,
                "summary": None,
                "published_at": published_at,
                "sentiment": "neutral",
                "importance": importance,
                "collected_at": self._now(),
            })
        return items

    # ------------------------------------------------------------------
    # 标准化方法（同步）
    # ------------------------------------------------------------------

    def _normalize_quote(self, raw: dict, symbol: str) -> dict:
        last_val = _try_number(raw.get("last", ""))
        open_val = _try_number(raw.get("open", ""))
        prev_close = _try_number(raw.get("prev_close", raw.get("pre_close", raw.get("settlement"))))
        if prev_close is None:
            change_val = _try_number(raw.get("change", raw.get("chg", "")))
            if isinstance(last_val, (int, float)) and isinstance(change_val, (int, float)):
                prev_close = last_val - change_val
        change = None
        if isinstance(prev_close, (int, float)) and isinstance(last_val, (int, float)):
            change = last_val - prev_close
        return {
            "symbol": symbol,
            "price": last_val if isinstance(last_val, (int, float)) else None,
            "change": change,
            "change_pct": _try_number(raw.get("percent", raw.get("chg_rate", raw.get("涨跌幅")))),
            "open": open_val if isinstance(open_val, (int, float)) else None,
            "high": _try_number(raw.get("high", "")),
            "low": _try_number(raw.get("low", "")),
            "prev_close": prev_close,
            "volume": _try_number(raw.get("volume", "")),
            "amount": _try_number(raw.get("amount", "")),
            "amplitude": None,
            "turnover_rate": None,
            "high_52w": None,
            "low_52w": None,
            "source": "westock",
            "collected_at": self._now(),
        }

    def _normalize_kline(self, raw: dict, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "date": raw.get("date", ""),
            "open": _try_number(raw.get("open", "")),
            "high": _try_number(raw.get("high", "")),
            "low": _try_number(raw.get("low", "")),
            "close": _try_number(raw.get("last", "")),
            "volume": _try_number(raw.get("volume", "")),
            "amount": _try_number(raw.get("amount", "")),
            "change_pct": _try_number(raw.get("percent", raw.get("chg_rate", raw.get("涨跌幅")))),
            "source": "westock",
            "collected_at": self._now(),
        }

    def _normalize_finance(self, tables: list[list[dict[str, str]]], symbol: str) -> dict:
        flat: dict[str, str] = {}
        for table in tables:
            if table:
                flat.update(table[0])

        def _n(key: str) -> str | int | float | None:
            v = flat.get(key, "")
            if v is None or v == "":
                return None
            return _try_number(v)

        revenue = _n("OperatingRevenue")
        net_profit = _n("NPParentCompanyOwners")
        total_assets = _n("TotalAssets")
        total_liability = _n("TotalLiability")
        se_wo_mi = _n("SEWithoutMI")

        gross_margin = None
        if revenue and isinstance(revenue, (int, float)):
            operating_cost = _n("OperatingCost")
            if operating_cost and isinstance(operating_cost, (int, float)):
                gross_margin = round((revenue - operating_cost) / revenue * 100, 2)

        net_margin = None
        if revenue and isinstance(revenue, (int, float)) and net_profit and isinstance(net_profit, (int, float)):
            net_margin = round(net_profit / revenue * 100, 2)

        roe = None
        if net_profit and isinstance(net_profit, (int, float)) and se_wo_mi and isinstance(se_wo_mi, (int, float)):
            roe = round(net_profit / se_wo_mi * 100, 2)

        debt_ratio = None
        if total_assets and isinstance(total_assets, (int, float)) and total_liability and isinstance(total_liability, (int, float)):
            debt_ratio = round(total_liability / total_assets * 100, 2)

        return {
            "symbol": symbol,
            "report_period": flat.get("EndDate", ""),
            "revenue": revenue,
            "revenue_yoy": None,
            "net_profit": net_profit,
            "net_profit_yoy": None,
            "eps": _n("BasicEPS"),
            "roe": roe,
            "debt_ratio": debt_ratio,
            "gross_margin": gross_margin,
            "net_margin": net_margin,
            "source": "westock",
            "collected_at": self._now(),
        }

    def _normalize_fund_flow(self, raw: dict, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "date": raw.get("EndDate", raw.get("date", "")),
            "main_net_inflow": _try_number(raw.get("MainNetFlow", "")),
            "super_large_net_inflow": _try_number(raw.get("JumboNetFlow", "")),
            "large_net_inflow": _try_number(raw.get("BlockNetFlow", "")),
            "medium_net_inflow": _try_number(raw.get("MidNetFlow", "")),
            "small_net_inflow": _try_number(raw.get("SmallNetFlow", "")),
            "net_inflow_ratio": _try_number(raw.get("MainInflowCircRate", "")),
            "source": "westock",
            "collected_at": self._now(),
        }

    def _normalize_technical(self, raw: dict, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "date": raw.get("date", ""),
            "ma5": _try_number(raw.get("ma.MA_5", "")),
            "ma10": _try_number(raw.get("ma.MA_10", "")),
            "ma20": _try_number(raw.get("ma.MA_20", "")),
            "ma60": _try_number(raw.get("ma.MA_60", "")),
            "macd_dif": _try_number(raw.get("macd.DIF", "")),
            "macd_dea": _try_number(raw.get("macd.DEA", "")),
            "macd_histogram": _try_number(raw.get("macd.MACD", "")),
            "rsi6": _try_number(raw.get("rsi.RSI_6", "")),
            "rsi14": _try_number(raw.get("rsi.RSI_12", "")),
            "boll_upper": _try_number(raw.get("boll.BOLL_UPPER", "")),
            "boll_middle": _try_number(raw.get("boll.BOLL_MID", "")),
            "boll_lower": _try_number(raw.get("boll.BOLL_LOWER", "")),
            "volume_ma5": _try_number(raw.get("ma.VOL_5", "")),
            "volume_ma20": _try_number(raw.get("ma.VOL_20", "")),
            "source": "westock",
            "collected_at": self._now(),
        }

    @staticmethod
    def _fund_flow_cmd(symbol: str) -> str:
        prefix = symbol[:2].lower()
        if prefix in _A_SHARE_PREFIXES:
            return "asfund"
        if prefix == "hk":
            return "hkfund"
        if prefix == "us":
            return "usfund"
        return "asfund"

    # ------------------------------------------------------------------
    # 扩展方法（异步版）
    # ------------------------------------------------------------------

    async def minute(self, symbol: str, days: int = 1) -> list[dict]:
        tables, err = await self._run_cli(f"minute {symbol} --days {days}")
        if err or not tables:
            return []
        results: list[dict] = []
        for row in tables[0]:
            results.append(self._normalize_minute_row(row, symbol))
        return results

    async def dividend(self, symbol: str) -> list[dict]:
        tables, err = await self._run_cli(f"dividend {symbol}")
        if err or not tables:
            return []
        results: list[dict] = []
        for row in tables[0]:
            results.append(self._normalize_dividend(row, symbol))
        return results

    async def shareholder(self, symbol: str) -> dict:
        tables, err = await self._run_cli(f"shareholder {symbol}")
        if err or not tables:
            return {}
        return self._normalize_shareholder(tables, symbol)

    async def reserve(self, symbol: str) -> dict:
        tables, err = await self._run_cli(f"reserve {symbol}")
        if err or not tables:
            return {"symbol": symbol, "source": "westock", "collected_at": self._now()}
        return self._normalize_reserve(tables, symbol)

    # ------------------------------------------------------------------
    # 标准化方法（同步）
    # ------------------------------------------------------------------

    def _normalize_minute_row(self, raw: dict, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "time": raw.get("time", ""),
            "price": _try_number(raw.get("price", "")),
            "volume": _try_number(raw.get("volume", "")),
            "avg_price": _try_number(raw.get("avg_price", "")),
            "source": "westock",
            "collected_at": self._now(),
        }

    def _normalize_dividend(self, raw: dict, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "ex_date": raw.get("ex_date", raw.get("ex_dividend_date", "")),
            "cash_dividend": _try_number(raw.get("cash_dividend", raw.get("CashDiv", ""))),
            "share_bonus": _try_number(raw.get("share_bonus", raw.get("BonusShareRatio", ""))),
            "record_date": raw.get("record_date", raw.get("recordDate", "")),
            "announce_date": raw.get("announce_date", raw.get("announceDate", "")),
            "dividend_year": raw.get("dividend_year", raw.get("year", "")),
            "source": "westock",
            "collected_at": self._now(),
        }

    def _normalize_shareholder(self, tables: list[list[dict[str, str]]], symbol: str) -> dict:
        result: dict = {
            "symbol": symbol,
            "source": "westock",
            "collected_at": self._now(),
        }
        share_holders: list[dict] = []
        if tables and tables[0]:
            for row in tables[0]:
                share_holders.append({
                    "rank": _try_number(row.get("rank", row.get("HolderRank", ""))),
                    "name": row.get("name", row.get("HolderName", "")),
                    "shares": _try_number(row.get("shares", row.get("HoldAmount", ""))),
                    "ratio": _try_number(row.get("ratio", row.get("HoldPercent", ""))),
                    "change": _try_number(row.get("change", row.get("Change", ""))),
                })
        result["top_shareholders"] = share_holders

        holder_count: list[dict] = []
        if len(tables) >= 2 and tables[1]:
            for row in tables[1]:
                holder_count.append({
                    "date": row.get("date", row.get("EndDate", "")),
                    "total_holders": _try_number(row.get("total_holders", row.get("HolderTotal", ""))),
                    "avg_shares": _try_number(row.get("avg_shares", row.get("AvgShares", ""))),
                })
        result["holder_count_history"] = holder_count
        return result

    def _normalize_reserve(self, tables: list[list[dict[str, str]]], symbol: str) -> dict:
        if not tables or not tables[0]:
            return {
                "symbol": symbol,
                "source": "westock",
                "collected_at": self._now(),
            }
        row = tables[0][0]
        return {
            "symbol": symbol,
            "report_period": row.get("report_period", row.get("ReportDate", "")),
            "forecast_type": row.get("forecast_type", row.get("ForcastType", "")),
            "profit_lower": _try_number(row.get("profit_lower", row.get("NetProfitLow", ""))),
            "profit_upper": _try_number(row.get("profit_upper", row.get("NetProfitHigh", ""))),
            "change_lower": _try_number(row.get("change_lower", row.get("ChangeLow", ""))),
            "change_upper": _try_number(row.get("change_upper", row.get("ChangeHigh", ""))),
            "summary": row.get("summary", row.get("Summary", "")),
            "source": "westock",
            "collected_at": self._now(),
        }

    # ------------------------------------------------------------------
    # 阶段 14：ETF 全套（5 个方法 + 5 个 _normalize）
    # westock CLI: etf / etf-holdings / etf-nav / etf-holders / etf-financial
    # ------------------------------------------------------------------

    async def etf_info(self, symbol: str) -> dict:
        """获取 ETF 基本信息 + 行情（含 etfType/trackIndex/returns/drawdown）。

        返回单条 dict（CLI 单行输出）。
        """
        tables, err = await self._run_cli(f"etf {symbol}")
        if err or not tables or not tables[0]:
            return {
                "symbol": symbol,
                "source": "westock",
                "collected_at": self._now(),
            }
        return self._normalize_etf_info(tables[0][0], symbol)

    async def etf_holdings(self, symbol: str) -> list[dict]:
        """获取 ETF 成分股持仓（多行）。"""
        tables, err = await self._run_cli(f"etf-holdings {symbol}")
        if err or not tables or not tables[0]:
            return []
        return [self._normalize_etf_holding_row(row, symbol) for row in tables[0]]

    async def etf_nav(self, symbol: str, start: str, end: str) -> list[dict]:
        """获取 ETF 历史净值（多行，需 start/end 日期）。"""
        tables, err = await self._run_cli(
            f"etf-nav {symbol} --start {start} --end {end}"
        )
        if err or not tables or not tables[0]:
            return []
        return [self._normalize_etf_nav_row(row, symbol) for row in tables[0]]

    async def etf_holders(self, symbol: str) -> dict:
        """获取 ETF 持有人结构（单条 dict）。"""
        tables, err = await self._run_cli(f"etf-holders {symbol}")
        if err or not tables or not tables[0]:
            return {
                "symbol": symbol,
                "source": "westock",
                "collected_at": self._now(),
            }
        return self._normalize_etf_holders(tables[0][0], symbol)

    async def etf_financial(self, symbol: str) -> dict:
        """获取 ETF 资产配置（股票/债券/商品/基金占比，单条 dict）。"""
        tables, err = await self._run_cli(f"etf-financial {symbol}")
        if err or not tables or not tables[0]:
            return {
                "symbol": symbol,
                "source": "westock",
                "collected_at": self._now(),
            }
        return self._normalize_etf_financial(tables[0][0], symbol)

    # ------------------------------------------------------------------
    # 阶段 14：ETF 5 个 _normalize
    # 兼容中英文字段别名（westock CLI 不同版本字段名可能不同）
    # ------------------------------------------------------------------

    def _normalize_etf_info(self, raw: dict, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "date": raw.get("date", ""),
            "etf_type": raw.get("etfType", ""),
            "establish_date": raw.get("establishDate", ""),
            "track_index_code": raw.get("trackIndexCode", ""),
            "track_index_name": raw.get("trackIndexName", ""),
            "manage_institution": raw.get("manageInstitution", ""),
            "close_price": _try_number(raw.get("closePrice", "")),
            "change_pct": _try_number(raw.get("changePct", "")),
            "total_mv": _try_number(raw.get("totalMV", "")),
            "shares": _try_number(raw.get("shares", "")),
            "shares_chg": _try_number(raw.get("sharesChg", "")),
            "nav": _try_number(raw.get("nav", "")),
            "disc": _try_number(raw.get("disc", "")),
            "ytd_return": _try_number(raw.get("ytdReturn", "")),
            "return_1m": _try_number(raw.get("return1M", "")),
            "return_3m": _try_number(raw.get("return3M", "")),
            "return_6m": _try_number(raw.get("return6M", "")),
            "return_1y": _try_number(raw.get("return1Y", "")),
            "return_3y": _try_number(raw.get("return3Y", "")),
            "max_drawdown_1m": _try_number(raw.get("maxDrawdown1M", "")),
            "max_drawdown_3m": _try_number(raw.get("maxDrawdown3M", "")),
            "max_drawdown_6m": _try_number(raw.get("maxDrawdown6M", "")),
            "max_drawdown_1y": _try_number(raw.get("maxDrawdown1Y", "")),
            "max_drawdown_3y": _try_number(raw.get("maxDrawdown3Y", "")),
            "source": "westock",
            "collected_at": self._now(),
        }

    def _normalize_etf_holding_row(self, raw: dict, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "constituent_code": raw.get("code", ""),
            "constituent_name": raw.get("name", ""),
            "ratio": _try_number(raw.get("ratio", "")),
            "date": raw.get("date", ""),
            "source": "westock",
            "collected_at": self._now(),
        }

    def _normalize_etf_nav_row(self, raw: dict, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "date": raw.get("date", ""),
            "nav": _try_number(raw.get("nav", "")),
            "nav_change": _try_number(raw.get("navChange", "")),
            "nav_change_pct": _try_number(raw.get("navChangePct", "")),
            "acc_nav": _try_number(raw.get("accNav", "")),
            "source": "westock",
            "collected_at": self._now(),
        }

    def _normalize_etf_holders(self, raw: dict, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "report_date": raw.get("date", ""),
            "holder_account": _try_number(raw.get("holderAccount", "")),
            "individual_holder_share": _try_number(raw.get("individualHolderShare", "")),
            "individual_holder_ratio": _try_number(raw.get("individualHolderRatio", "")),
            "institution_holder_share": _try_number(raw.get("institutionHolderShare", "")),
            "institution_holder_ratio": _try_number(raw.get("institutionHolderRatio", "")),
            "top10_share": _try_number(raw.get("top10Share", "")),
            "top10_ratio": _try_number(raw.get("top10Ratio", "")),
            "source": "westock",
            "collected_at": self._now(),
        }

    def _normalize_etf_financial(self, raw: dict, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "date": raw.get("date", ""),
            "total_assets": _try_number(raw.get("totalAssets", "")),
            "stock_ratio": _try_number(raw.get("stockRatio", "")),
            "bond_ratio": _try_number(raw.get("bondRatio", "")),
            "commodity_ratio": _try_number(raw.get("commodityRatio", "")),
            "fund_ratio": _try_number(raw.get("fundRatio", "")),
            "key_asset_ratio": _try_number(raw.get("keyAssetRatio", "")),
            "source": "westock",
            "collected_at": self._now(),
        }

    # ------------------------------------------------------------------
    # 阶段 8 修正：板块首页 (board) + 热门板块 (hot board)
    # ------------------------------------------------------------------

    async def board_sectors(self) -> list[dict]:
        """调 board，合并 3 张表（行业涨幅/概念涨幅/行业资金流入 Top5）为统一 list。

        sector_type 字段强制注入，避免 UNIQUE(name, date, sector_type, source)
        在 3 类数据合并时丢失分类信息。
        """
        tables, err = await self._run_cli("board")
        if err or not tables:
            return []
        results: list[dict] = []
        # board 返回 3 张表: [0] 行业涨幅 / [1] 概念涨幅 / [2] 行业资金流入 Top5
        type_table_pairs: list[tuple[str, list[dict]]] = []
        if len(tables) > 0 and tables[0] is not None:
            type_table_pairs.append(("industry", tables[0]))
        if len(tables) > 1 and tables[1] is not None:
            type_table_pairs.append(("concept", tables[1]))
        if len(tables) > 2 and tables[2] is not None:
            type_table_pairs.append(("fund_flow", tables[2]))
        for sector_type, table in type_table_pairs:
            for row in table:
                results.append(self._normalize_board_sector_row(row, sector_type))
        return results

    async def hot_sectors(self, limit: int = 10) -> list[dict]:
        """调 hot board，返回热门板块（默认前 10）。

        CLI 返回的每行带 symbol (如 pt01801161) + name + zdf (涨幅) + zxj (最新价) +
        rank + rankdelta + stock_type (BK-HY-2=行业 / BK=概念)。
        """
        tables, err = await self._run_cli(f"hot board --limit {limit}")
        if err or not tables or not tables[0]:
            return []
        return [self._normalize_hot_sector_row(row) for row in tables[0]]

    def _normalize_board_sector_row(
        self, raw: dict, sector_type: str
    ) -> dict:
        """board 输出字段:
        - 行业/概念涨幅: name / changePct / turnoverRate / changePct5d /
          changePct20d / leadStock
        - 行业资金流入 Top5: name / changePct / mainNetInflow /
          mainNetInflow5d / upDownRatio
        """
        return {
            "name": raw.get("name", ""),
            "date": raw.get("date", ""),
            "sector_type": sector_type,
            "symbol": None,
            "change_pct": _try_number(raw.get("changePct")),
            "turnover_rate": _try_number(raw.get("turnoverRate")),
            "change_pct_5d": _try_number(raw.get("changePct5d")),
            "change_pct_20d": _try_number(raw.get("changePct20d")),
            "lead_stock": raw.get("leadStock"),
            "main_net_inflow": _try_number(raw.get("mainNetInflow")),
            "main_net_inflow_5d": _try_number(raw.get("mainNetInflow5d")),
            "up_down_ratio": _try_number(raw.get("upDownRatio")),
            "rank": None,
            "zxj": None,
            "source": "westock",
            "collected_at": self._now(),
        }

    def _normalize_hot_sector_row(self, raw: dict) -> dict:
        """hot board 输出: index / level / symbol / rank / rankdelta / date /
        stock_type / name / zdf (涨幅) / zxj (最新价)。"""
        # hot board 的 stock_type: BK-HY-2=行业 / BK=概念 → sector_type 映射
        stype = raw.get("stock_type", "")
        if stype.startswith("BK-HY"):
            sector_type = "industry"
        elif stype == "BK":
            sector_type = "concept"
        else:
            sector_type = "industry"  # 默认行业
        return {
            "name": raw.get("name", ""),
            "date": (raw.get("date", "") or "").split(" ")[0],
            "sector_type": sector_type,
            "symbol": raw.get("symbol"),
            "change_pct": _try_number(raw.get("zdf")),
            "turnover_rate": None,
            "change_pct_5d": None,
            "change_pct_20d": None,
            "lead_stock": None,
            "main_net_inflow": None,
            "main_net_inflow_5d": None,
            "up_down_ratio": None,
            "rank": _try_number(raw.get("rank")),
            "zxj": _try_number(raw.get("zxj")),
            "source": "westock",
            "collected_at": self._now(),
        }
