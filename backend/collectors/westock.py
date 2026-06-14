import asyncio
import os
import re
import shutil
import subprocess
from datetime import datetime

from loguru import logger

from backend.collectors.base import BaseProvider
from backend.collectors.westock_normalizers import (
    _A_SHARE_PREFIXES,
    _extract_detail_rows,
    _fund_flow_cmd,
    _normalize_blocktrade_row,
    _normalize_board_sector_row,
    _normalize_chip_row,
    _normalize_dividend,
    _normalize_etf_financial,
    _normalize_etf_holding_row,
    _normalize_etf_holders,
    _normalize_etf_info,
    _normalize_etf_nav_row,
    _normalize_exdiv_row,
    _normalize_finance,
    _normalize_fund_flow,
    _normalize_hk_finance_row,
    _normalize_hot_sector_row,
    _normalize_ipo_row,
    _normalize_kline,
    _normalize_lhb_row,
    _normalize_margintrade_row,
    _normalize_minute_row,
    _normalize_quote,
    _normalize_reserve,
    _normalize_shareholder,
    _normalize_technical,
    _normalize_us_finance_row,
    _try_number,
)
_PERIOD_MAP: dict[str, str] = {
    "daily": "day",
    "weekly": "week",
    "monthly": "month",
}

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

# 错误码常量：固定枚举值，便于日志聚合和 UI 告警分类；
# 触发短语作 context 追加，不作为 error_message 主内容。
WESTOCK_EMPTY_OUTPUT: str = "WESTOCK_EMPTY_OUTPUT"
WESTOCK_NO_DATA: str = "WESTOCK_NO_DATA"
WESTOCK_QUERY_FAILED: str = "WESTOCK_QUERY_FAILED"
WESTOCK_EXEC_FAILED: str = "WESTOCK_EXEC_FAILED"
WESTOCK_CHANNEL_UNSUPPORTED: str = "WESTOCK_CHANNEL_UNSUPPORTED"
WESTOCK_UNKNOWN_SUBCMD: str = "WESTOCK_UNKNOWN_SUBCMD"
# Node.js 运行时偶发崩溃（CSPRNG 断言失败、InitializeOncePerProcess abort）。
# 与 EMPTY_OUTPUT 区分:Node 崩了 stdout 真空是「副作用」,EMPTY_OUTPUT 仅描述
# stdout 为空的事实；崩了本身需要重试 1-2 次（重启 Node 通常可恢复）。
WESTOCK_NODE_ABORT: str = "WESTOCK_NODE_ABORT"

# (正则, 错误码) 元组列表。**顺序就是匹配优先级**——更具体/更长的模式
# 必须排在更宽泛/更短的前面,避免被截胡。
# 优先级考量:执行失败 [XXX] 包含具体错误码 (如 SKILL_006),最具体 → 最先;
# 查询 XXX 失败 是宽泛业务错误,放后面;数据为空 是最模糊的兜底,放最后。
WESTOCK_ERROR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"执行失败\s*[\[【](\w*\d*)[\]】]\s*[:：]?\s*"), WESTOCK_EXEC_FAILED),
    (re.compile(r"查询\S+?失败\s*[:：]\s*"), WESTOCK_QUERY_FAILED),
    (
        re.compile(r"命令\s*[\"「'](.+?)[\"」']\s*在当前渠道不可用"),
        WESTOCK_CHANNEL_UNSUPPORTED,
    ),
    (re.compile(r"未知子命令\s*[\"「'](.+?)[\"」']"), WESTOCK_UNKNOWN_SUBCMD),
    (re.compile(r"数据为空"), WESTOCK_NO_DATA),
]

# Node.js 运行时崩溃堆栈特征（stderr 通道，Node 偶发崩溃如 CSPRNG 断言失败、
# InitializeOncePerProcess abort）。与上面业务错误码分开:Node 崩了时 stdout
# 真空,会被误判为 EMPTY_OUTPUT,所以单独识别后走重试路径。
WESTOCK_NODE_ABORT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"Assertion failed:.*CSPRNG", re.IGNORECASE),
    re.compile(r"node::InitializeOncePerProcessInternal", re.IGNORECASE),
    re.compile(r"Native stack trace"),
]

def _detect_error(text: str) -> tuple[str, str] | None:
    """从 westock CLI 输出提取错误。

    Returns:
        (error_code, context) 或 None（无错误）。
        error_code 是固定错误码常量；context 是触发短语（带原文中
        的实际信息，如 SKILL_006 编号、具体命令名等），便于调试。
    """
    if not text.strip():
        return (WESTOCK_EMPTY_OUTPUT, "CLI 返回空输出")
    for pattern, code in WESTOCK_ERROR_PATTERNS:
        m = pattern.search(text)
        if m:
            context = m.group(0).strip()
            return (code, context)
    return None

def _detect_node_abort(stderr: str) -> str | None:
    """检测 Node.js 运行时崩溃（CSPRNG 断言失败 / InitializeOncePerProcess abort）。

    Node 偶发崩溃时 stdout 真空、stderr 是英文 native stack trace,既不会被
    WESTOCK_ERROR_PATTERNS 命中,也不该被当 EMPTY_OUTPUT 吞掉。匹配到时
    返回第一行触发短语,供日志/UI 区分。
    """
    if not stderr or not isinstance(stderr, str):
        return None
    for pattern in WESTOCK_NODE_ABORT_PATTERNS:
        m = pattern.search(stderr)
        if m:
            return m.group(0).strip()
    return None

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
        # 2026-06-13 变更：从 `npx -y westock-data-clawhub@1.0.4` 改为通过
        # PowerShell 调用 `npm i -g` 全局装的 wrapper。绕开两个问题：
        # 1) npx 每次冷启动新 Node 进程，Windows + Node 24 偶发 ncrypto::CSPRNG
        #    断言失败（rc=134）；
        # 2) Python `subprocess.run` 在 MSYS 启动的 Python 下直接调 `node.exe`，
        #    同样 100% 撞 CSPRNG 断言（Node 进程父进程栈被 MSYS 干扰）。
        # 验证：PowerShell 调 westock-data-clawhub 10/10 稳定。PowerShell 自带
        # PATHEXT、npm 全局 PATH 解析，不依赖 git-bash。
        self.command: str = self.params.get("command", "westock-data-clawhub")
        # 探测 PowerShell（PowerShell 7 优先于 Windows PowerShell 5.1）和
        # npm 全局装的 westock wrapper。两者都拿到才走 PowerShell 模式；
        # 缺一则仅打 warning,后续 _run_cli 会发现 self._westock_wrapper 是
        # None,直接返回空。
        # 兜底：探测失败时回退到 self.command 字面值（测试环境无全局 westock
        # 但仍可 mock subprocess.run 验证业务逻辑；生产环境探测成功优先）。
        self._powershell_exe: str | None = (
            shutil.which("pwsh") or shutil.which("powershell")
        )
        self._westock_wrapper: str | None = (
            shutil.which(self.command) or self.command
        )
        if not (self._powershell_exe and self._westock_wrapper):
            logger.warning(
                "WeStock 找不到 PowerShell 或全局 wrapper (powershell=%r, wrapper=%r);"
                "quote/kline 等数据采集将失败。建议: 1) 装 PowerShell 7 "
                "(`winget install Microsoft.PowerShell`)  2) `npm i -g westock-data-clawhub@1.0.4`",
                self._powershell_exe,
                self._westock_wrapper,
            )

    async def _run_cli(
        self, args: str
    ) -> tuple[list[list[dict[str, str]]], str | None]:
        # 走 PowerShell 调全局 westock wrapper:
        # `powershell.exe -NoProfile -Command "& '<wrapper>' <args>"`
        if not (self._powershell_exe and self._westock_wrapper):
            # __init__ 探测失败时已 warning,业务调用静默返回空结果
            return [], "WeStock 未配置（缺 PowerShell 或全局 wrapper）"
        # -NoProfile 避免加载用户 profile 拖慢启动;
        # 单引号包 wrapper 路径防空格；args 直接拼（westock 参数是
        # `--k=v` 风格不会被 PowerShell 解释）
        ps_command = f"& '{self._westock_wrapper}' {args}"
        cmd_parts: list[str] = [self._powershell_exe, "-NoProfile", "-Command", ps_command]

        # SKILL_006 是 westock CLI 的冷启动失败——首次调用偶发返回，
        # 重试 1-2 次即恢复。TimeoutExpired 同理（CLI 冷启动慢）。
        # 其它错误（参数错 / 数据源无数据）立即返回，避免无谓重试。
        # env 透传父进程:PowerShell 需要 PATHEXT、PATH 等解析 wrapper,
        # 裁剪会破坏 npm 全局 PATH 解析。本工具是单用户本地进程,
        # 父 env 泄漏风险可接受。
        last_err: str | None = None
        for attempt in range(_MAX_RETRIES + 1):
            # 通过 subprocess.run（模块级引用，便于测试 mock）调用 CLI，
            # 并用 asyncio.to_thread 避免阻塞事件循环。
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    cmd_parts,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    env=os.environ.copy(),
                )
            except subprocess.TimeoutExpired:
                last_err = f"CLI 超时 ({self.timeout}s)"
                logger.warning(
                    "WeStock CLI 超时 [attempt {}/{}]: cmd={}",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    cmd_parts,
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

            # Node.js 运行时崩溃（CSPRNG 断言 / InitializeOncePerProcess abort）
            # 比业务错误优先:崩溃时 stdout 真空,会被 _detect_error 误判为
            # EMPTY_OUTPUT,语义上不对（EMPTY_OUTPUT 描述 stdout 真空的事实,
            # 崩了是另一回事）。统一在 _detect_error 之前识别,然后走重试。
            node_abort = _detect_node_abort(stderr)
            if node_abort and attempt < _MAX_RETRIES:
                last_err = f"{WESTOCK_NODE_ABORT}: {node_abort}"
                logger.warning(
                    "WeStock Node 运行时崩溃 [attempt {}/{}]: cmd={}, error={}",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    cmd_parts,
                    last_err,
                )
                await asyncio.sleep(_RETRY_BACKOFF * (attempt + 1))
                continue
            if node_abort:
                last_err = f"{WESTOCK_NODE_ABORT}: {node_abort}"
                logger.warning(
                    "WeStock Node 运行时崩溃（重试耗尽）: cmd={}, error={}",
                    cmd_parts,
                    last_err,
                )
                return [], last_err

            error = _detect_error(stdout)
            if error:
                code, context = error
                # 组合成单一错误字符串：error_code（固定枚举）+ context（触发短语）
                # 保留 SKILL_006 等关键文本供下游"in"检查。
                last_err = f"{code}: {context}" if context else code
                # 仅 SKILL_006 重试（冷启动缓解），其它业务错误立即返回
                is_skill_006 = "SKILL_006" in context
                if is_skill_006 and attempt < _MAX_RETRIES:
                    logger.warning(
                        "WeStock CLI 冷启动失败 [attempt {}/{}]: cmd={}, error={}",
                        attempt + 1,
                        _MAX_RETRIES + 1,
                        cmd_parts,
                        last_err,
                    )
                    await asyncio.sleep(_RETRY_BACKOFF * (attempt + 1))
                    continue
                logger.warning(
                    "WeStock CLI 业务错误: cmd={}, error={}", cmd_parts, last_err
                )
                return [], last_err

            if proc.returncode != 0:
                # 非零退出码立即返回，不重试（重试也无法修复 CLI bug；
                # Node 偶发崩溃的情况已在前面的 _detect_node_abort 处理）
                msg = (
                    stderr.strip()
                    or stdout.strip()[:200]
                    or f"exit code {proc.returncode}"
                )
                logger.warning(
                    "WeStock CLI 非零退出: rc={}, msg={}", proc.returncode, msg
                )
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
            {
                "code": r.get("code", ""),
                "name": r.get("name", ""),
                "type": r.get("type", ""),
            }
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
                return [_normalize_quote(row, sym, self._now()) for row in tables[0]]

        nested = await asyncio.gather(*(_fetch_one(s) for s in symbols))
        results: list[dict] = []
        for chunk in nested:
            results.extend(chunk)
        return results

    async def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        cli_period = _PERIOD_MAP.get(period, "day")
        tables, err = await self._run_cli(
            f"kline {symbol} --period {cli_period} --limit 60"
        )
        if err or not tables:
            return []
        results: list[dict] = []
        for row in tables[0]:
            results.append(_normalize_kline(row, symbol, self._now()))
        return results

    async def finance(self, symbol: str) -> dict:
        tables, err = await self._run_cli(f"finance {symbol}")
        if err or not tables:
            return {}
        return _normalize_finance(tables, symbol, self._now())

    async def fund_flow(self, symbol: str) -> dict:
        fund_cmd = _fund_flow_cmd(symbol)
        tables, err = await self._run_cli(f"{fund_cmd} {symbol}")
        if err or not tables:
            return {}
        row = tables[0][0] if tables[0] else {}
        return _normalize_fund_flow(row, symbol, self._now())

    async def technical(self, symbol: str) -> dict:
        tables, err = await self._run_cli(f"technical {symbol}")
        if err or not tables:
            return {}
        row = tables[0][0] if tables[0] else {}
        return _normalize_technical(row, symbol, self._now())

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
                    published_at = datetime.fromtimestamp(
                        float(ts), tz=_tz.utc
                    ).isoformat()
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
            items.append(
                {
                    "title": row.get("news_title", ""),
                    "source": row.get("source", ""),
                    "url": f"wehot://{news_id}" if news_id else None,
                    "content": None,
                    "summary": None,
                    "published_at": published_at,
                    "sentiment": "neutral",
                    "importance": importance,
                    "collected_at": self._now(),
                }
            )
        return items

    # ------------------------------------------------------------------
    # 标准化方法（同步）
    # ------------------------------------------------------------------

    async def minute(self, symbol: str, days: int = 1) -> list[dict]:
        tables, err = await self._run_cli(f"minute {symbol} --days {days}")
        if err or not tables:
            return []
        results: list[dict] = []
        for row in tables[0]:
            results.append(_normalize_minute_row(row, symbol, self._now()))
        return results

    async def dividend(self, symbol: str) -> list[dict]:
        tables, err = await self._run_cli(f"dividend {symbol}")
        if err or not tables:
            return []
        results: list[dict] = []
        for row in tables[0]:
            results.append(_normalize_dividend(row, symbol, self._now()))
        return results

    async def shareholder(self, symbol: str) -> dict:
        tables, err = await self._run_cli(f"shareholder {symbol}")
        if err or not tables:
            return {}
        return _normalize_shareholder(tables, symbol, self._now())

    async def reserve(self, symbol: str) -> dict:
        tables, err = await self._run_cli(f"reserve {symbol}")
        if err or not tables:
            return {"symbol": symbol, "source": "westock", "collected_at": self._now()}
        return _normalize_reserve(tables, symbol, self._now())

    # ------------------------------------------------------------------
    # 标准化方法（同步）
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
        return _normalize_etf_info(tables[0][0], symbol, self._now())

    async def etf_holdings(self, symbol: str) -> list[dict]:
        """获取 ETF 成分股持仓（多行）。"""
        tables, err = await self._run_cli(f"etf-holdings {symbol}")
        if err or not tables or not tables[0]:
            return []
        return [_normalize_etf_holding_row(row, symbol, self._now()) for row in tables[0]]

    async def etf_nav(self, symbol: str, start: str, end: str) -> list[dict]:
        """获取 ETF 历史净值（多行，需 start/end 日期）。"""
        tables, err = await self._run_cli(
            f"etf-nav {symbol} --start {start} --end {end}"
        )
        if err or not tables or not tables[0]:
            return []
        return [_normalize_etf_nav_row(row, symbol, self._now()) for row in tables[0]]

    async def etf_holders(self, symbol: str) -> dict:
        """获取 ETF 持有人结构（单条 dict）。"""
        tables, err = await self._run_cli(f"etf-holders {symbol}")
        if err or not tables or not tables[0]:
            return {
                "symbol": symbol,
                "source": "westock",
                "collected_at": self._now(),
            }
        return _normalize_etf_holders(tables[0][0], symbol, self._now())

    async def etf_financial(self, symbol: str) -> dict:
        """获取 ETF 资产配置（股票/债券/商品/基金占比，单条 dict）。"""
        tables, err = await self._run_cli(f"etf-financial {symbol}")
        if err or not tables or not tables[0]:
            return {
                "symbol": symbol,
                "source": "westock",
                "collected_at": self._now(),
            }
        return _normalize_etf_financial(tables[0][0], symbol, self._now())

    # ------------------------------------------------------------------
    # 阶段 14：ETF 5 个 _normalize
    # 兼容中英文字段别名（westock CLI 不同版本字段名可能不同）
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
                results.append(_normalize_board_sector_row(row, sector_type, self._now()))
        return results

    async def hot_sectors(self, limit: int = 10) -> list[dict]:
        """调 hot board，返回热门板块（默认前 10）。

        CLI 返回的每行带 symbol (如 pt01801161) + name + zdf (涨幅) + zxj (最新价) +
        rank + rankdelta + stock_type (BK-HY-2=行业 / BK=概念)。
        """
        tables, err = await self._run_cli(f"hot board --limit {limit}")
        if err or not tables or not tables[0]:
            return []
        return [_normalize_hot_sector_row(row, self._now()) for row in tables[0]]

    async def us_finance(
        self,
        symbol: str,
        ftype: str = "income",
        num: int = 4,
    ) -> list[dict]:
        """美股财务（us 前缀）：type ∈ {income, balance, cashflow}。

        返回多期 list[dict]，每期对应 1 行（end_date / period_type）。
        """
        tables, err = await self._run_cli(
            f"finance {symbol} --type {ftype} --num {num}"
        )
        if err or not tables:
            return []
        results: list[dict] = []
        for table in tables:
            for row in table:
                results.append(_normalize_us_finance_row(row, symbol, ftype, self._now()))
        return results

    async def hk_finance(
        self,
        symbol: str,
        ftype: str = "zhsy",
        num: int = 4,
    ) -> list[dict]:
        """港股财务（hk 前缀）：type ∈ {zhsy, zcfz, xjll}（中文拼音首字母）。"""
        tables, err = await self._run_cli(
            f"finance {symbol} --type {ftype} --num {num}"
        )
        if err or not tables:
            return []
        results: list[dict] = []
        for table in tables:
            for row in table:
                results.append(_normalize_hk_finance_row(row, symbol, ftype, self._now()))
        return results

    # ------------------------------------------------------------------
    # 阶段 15：2 个 _normalize（美股/港股 字段映射）
    # 美股 CLI 字段示例（实测 usAAPL）:
    #   income 表:  _date / BasicEPS / Sales / NetIncome / EBITDA / EBIT / ...
    #   balance 表: EndDate / TotalAssets / TotalLiabilities / TotalEquity / ...
    #   cashflow 表: EndDate / CFO / CFI / CFF / Capex / ...
    # 港股 zhsy 表:  _date / BasicEPS / OperatingIncome / OperatingProfit / ...
    # 港股 zcfz 表:  EndDate / TotalAssets / TotalLiability / SEWithoutMI / ...
    # 港股 xjll 表:  EndDate / NetOperateCashFlow / NetInvestCashFlow / ...
    # ------------------------------------------------------------------

    async def ipo_calendar(self, market: str) -> list[dict]:
        """新股日历（市场过滤，market ∈ {hk, us}）。"""
        tables, err = await self._run_cli(f"ipo {market}")
        if err or not tables or not tables[0]:
            return []
        return [_normalize_ipo_row(row, market, self._now()) for row in tables[0]]

    async def exdiv_calendar(self, symbol: str) -> list[dict]:
        """除权日历（港美单只股票）。A 股 exdiv 数据源死，此方法仅用于 hk/us。"""
        tables, err = await self._run_cli(f"exdiv {symbol}")
        if err or not tables or not tables[0]:
            return []
        return [_normalize_exdiv_row(row, symbol, self._now()) for row in tables[0]]

    async def chip_distribution(self, symbol: str) -> dict | None:
        """筹码成本分布（4 字段：profit_rate/avg_cost/concentration 90/70）。

        仅 A 股（sh/sz/bj）支持；港美股标的早退返回 None，避免触发 westock CLI 不存在的子命令。
        """
        if not symbol.startswith(_A_SHARE_PREFIXES):
            logger.debug("chip_distribution 仅支持 A 股，跳过: {}", symbol)
            return None
        tables, err = await self._run_cli(f"chip {symbol}")
        if err or not tables or not tables[0]:
            return {
                "symbol": symbol,
                "source": "westock",
                "collected_at": self._now(),
            }
        return _normalize_chip_row(tables[0][0], symbol, self._now())

    async def margintrade(self, symbol: str) -> dict | None:
        """融资融券（单条：finance/security value + DoD）。

        仅 A 股（sh/sz/bj）支持；港美股标的早退返回 None。
        """
        if not symbol.startswith(_A_SHARE_PREFIXES):
            logger.debug("margintrade 仅支持 A 股，跳过: {}", symbol)
            return None
        tables, err = await self._run_cli(f"margintrade {symbol}")
        if err or not tables or not tables[0]:
            return {
                "symbol": symbol,
                "source": "westock",
                "collected_at": self._now(),
            }
        return _normalize_margintrade_row(tables[0][0], symbol, self._now())

    async def blocktrade(self, symbol: str, date: str) -> dict | None:
        """大宗交易（单只 + 指定日期）。

        仅 A 股（sh/sz/bj）支持；港美股标的早退返回 None。

        返回结构包含两段信息：
        - 概览（tables[0][0]）: closePrice / changePct
        - 明细（tables[1]）: 成交价 / 成交额 / 折溢率 / 买卖营业部（按行展开，
          buy_department / sell_department 以 JSON 列表存于 TEXT 列）
        """
        if not symbol.startswith(_A_SHARE_PREFIXES):
            logger.debug("blocktrade 仅支持 A 股，跳过: {}", symbol)
            return None
        tables, err = await self._run_cli(f"blocktrade {symbol} --date {date}")
        if err or not tables:
            return None
        if not tables[0]:
            return {
                "symbol": symbol,
                "date": date,
                "source": "westock",
                "collected_at": self._now(),
            }
        return _normalize_blocktrade_row(tables, symbol, date, self._now())

    async def lhb(self, symbol: str, date: str) -> dict | None:
        """龙虎榜（单只 + 指定日期）。无数据时返回 None。

        仅 A 股（sh/sz/bj）支持；港美股标的早退返回 None。

        返回结构包含两段信息：
        - 概览（tables[0][0]）: closePrice / changePct / netBuyAmount
        - 明细（tables[1]）: 买方营业部 / 卖方营业部（多行 JSON 列表）
        """
        if not symbol.startswith(_A_SHARE_PREFIXES):
            logger.debug("lhb 仅支持 A 股，跳过: {}", symbol)
            return None
        tables, err = await self._run_cli(f"lhb {symbol} --date {date}")
        if err or not tables or not tables[0]:
            return None
        return _normalize_lhb_row(tables, symbol, date, self._now())

# ---- Normalizer/helper re-exports for backward compat ----
# 原 24 个 _normalize_* 方法 + 2 个 helper 已提取到 backend/collectors/westock_normalizers.py
# 保留类属性重导出，使 WeStockProvider._fund_flow_cmd / WeStockProvider._extract_detail_rows
# 旧调用方式（含测试代码 tests/collectors/test_westock.py:402-417）继续可用。
WeStockProvider._fund_flow_cmd = staticmethod(_fund_flow_cmd)
WeStockProvider._extract_detail_rows = staticmethod(_extract_detail_rows)
