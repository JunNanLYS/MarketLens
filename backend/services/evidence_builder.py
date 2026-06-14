"""证据构建器（异步版）——聚合各类数据为 AI 分析提供输入。

实现采用注册表（EVIDENCE_BUILDERS）驱动：
- 每条 EvidenceBuilderSpec 描述「读哪张表 / 怎么 SQL / 怎么后处理」
- build() / build_multi() 遍历注册表统一调度
- 新增数据源只需追加注册表条目
"""

import json
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Callable, Literal

from loguru import logger

from backend.config import get_config


@dataclass(frozen=True)
class EvidenceBuilderSpec:
    """注册表条目：单标的采集所需的一切。

    Attributes:
        key: 输出字典中的 key（如 "quote" / "kline"）
        table: 主表名（用于 schema 元信息）
        needs_symbol: True 时按标的查询；False 时为市场级共享数据（如 sector_context）
        postprocess: 后处理函数 (rows: list[dict], symbol: str | None) -> 目标值
            None 表示直接返回 rows 列表
        order_by_desc: SQL ORDER BY 子句（不含 ORDER BY 关键字）
        limit: LIMIT N（N 为 None 表示不带 LIMIT）
        postprocess_kind: 后处理类别，决定主入口如何处理返回值
            "list" -> 列表（如 kline）
            "dict_or_none" -> dict 或 None（如 quote）
            "wrapped_dict_or_none" -> 包装后 dict 或 None（如 dividends、finance）
            "special" -> 调度时单独处理（sector_context / us_finance / shareholders）
        multi_strategy: 多标的 (build_multi) 时的 SQL 策略
            "standard" -> 走通用 _fetch_rows_multi（普通 WHERE IN + ORDER BY + LIMIT per symbol）
            "max_per_symbol" -> 每标的最新的 N 行（quote / technical：MAX(date) 子查询）
            "special" -> 调度时单独处理（sector_context / us_finance / shareholders / news）
    """

    key: str
    table: str
    needs_symbol: bool
    postprocess: Callable | None
    order_by_desc: str | None
    limit: int | None
    postprocess_kind: Literal["list", "dict_or_none", "wrapped_dict_or_none", "special"]
    multi_strategy: Literal["standard", "max_per_symbol", "special"] = "standard"


def _ma_compute(items: list[dict]) -> list[dict]:
    """计算 MA(5/10/20/60)，滑动窗口 O(n)。

    直接修改 items 列表中的每个 dict 追加 ma5/ma10/ma20/ma60 字段。
    """
    closes = [item["close"] for item in items]
    ma_windows = (5, 10, 20, 60)
    running_sums: dict[int, float] = {w: 0.0 for w in ma_windows}
    for i, item in enumerate(items):
        c = closes[i]
        for w in ma_windows:
            running_sums[w] += c
            if i >= w:
                running_sums[w] -= closes[i - w]
            if i >= w - 1:
                item[f"ma{w}"] = round(running_sums[w] / w, 4)
            else:
                item[f"ma{w}"] = None
    return items


def _pp_quote(rows: list[dict], _symbol: str | None) -> dict | None:
    """quote: 取首行 dict，无则 None。"""
    return dict(rows[0]) if rows else None


def _pp_kline(rows: list[dict], _symbol: str | None) -> list[dict]:
    """kline: 反转（按日期升序）+ 计算 MA(5/10/20/60)。"""
    items = [dict(r) for r in rows]
    items.reverse()
    return _ma_compute(items)


def _pp_fund_flows(rows: list[dict], _symbol: str | None) -> list[dict]:
    """fund_flows: 反转（按日期升序）。"""
    items = [dict(r) for r in rows]
    items.reverse()
    return items


def _pp_finance(rows: list[dict], _symbol: str | None) -> dict | None:
    """finance: 调 _derive_finance_yoy。"""
    return EvidenceBuilder._derive_finance_yoy([dict(r) for r in rows])


def _pp_dividends(rows: list[dict], _symbol: str | None) -> dict | None:
    """dividends: 包装 history + latest_* + source。"""
    if not rows:
        return None
    return {
        "history": [dict(r) for r in rows],
        "latest_cash_dividend": rows[0]["cash_dividend"],
        "latest_ex_date": rows[0]["ex_date"],
        "source": rows[0].get("source"),
    }


def _pp_shareholders_top(rows: list[dict], _symbol: str | None) -> list[dict]:
    """shareholders (top): 转 list[dict]，无修改。"""
    return [dict(r) for r in rows]


def _pp_shareholders_count(rows: list[dict], _symbol: str | None) -> list[dict]:
    """shareholders (count): 转 list[dict]，无修改。"""
    return [dict(r) for r in rows]


def _pp_forecasts(rows: list[dict], _symbol: str | None) -> dict | None:
    """forecasts: 包装 history + latest + source。"""
    if not rows:
        return None
    return {
        "history": [dict(r) for r in rows],
        "latest": dict(rows[0]),
        "source": rows[0].get("source"),
    }


def _pp_sector_context(_rows: list[dict] | None, _symbol: str | None) -> dict | None:
    """sector_context 特殊：需 3 个独立查询，主入口调度时单独处理。"""
    # 实际逻辑在 build() 内部实现，postprocess 不直接使用
    raise NotImplementedError("sector_context 调度在 build() 中特殊处理")


def _pp_news(rows: list[dict], _symbol: str | None) -> dict | None:
    """news: 调 _aggregate_news。"""
    items = [dict(r) for r in rows]
    return EvidenceBuilder._aggregate_news(items)


def _pp_technical(rows: list[dict], _symbol: str | None) -> dict | None:
    """technical: 取首行 + 加 prev_macd_histogram（如有第二行）。"""
    if not rows:
        return None
    latest = dict(rows[0])
    if len(rows) >= 2:
        latest["prev_macd_histogram"] = dict(rows[1]).get("macd_histogram")
    return latest


# 11 个注册表条目
# 排序：build() 内按注册表顺序输出；非 symbol 依赖（sector_context, news）单独处理
EVIDENCE_BUILDERS: tuple[EvidenceBuilderSpec, ...] = (
    EvidenceBuilderSpec(
        key="quote",
        table="market_quotes",
        needs_symbol=True,
        postprocess=_pp_quote,
        order_by_desc="collected_at",
        limit=1,
        postprocess_kind="dict_or_none",
        multi_strategy="max_per_symbol",
    ),
    EvidenceBuilderSpec(
        key="kline",
        table="kline_daily",
        needs_symbol=True,
        postprocess=_pp_kline,
        order_by_desc="date",
        limit="kline_limit",  # 由 _evidence_limits() 解析
        postprocess_kind="list",
    ),
    EvidenceBuilderSpec(
        key="fund_flows",
        table="fund_flows",
        needs_symbol=True,
        postprocess=_pp_fund_flows,
        order_by_desc="date",
        limit="fund_flow_limit",
        postprocess_kind="list",
    ),
    EvidenceBuilderSpec(
        key="finance",
        table="financial_reports",
        needs_symbol=True,
        postprocess=_pp_finance,
        order_by_desc="collected_at",
        limit="finance_limit",
        postprocess_kind="wrapped_dict_or_none",
    ),
    EvidenceBuilderSpec(
        key="dividends",
        table="dividends",
        needs_symbol=True,
        postprocess=_pp_dividends,
        order_by_desc="ex_date",
        limit=4,
        postprocess_kind="wrapped_dict_or_none",
    ),
    EvidenceBuilderSpec(
        key="forecasts",
        table="profit_forecasts",
        needs_symbol=True,
        postprocess=_pp_forecasts,
        order_by_desc="report_period",
        limit=4,
        postprocess_kind="wrapped_dict_or_none",
    ),
    EvidenceBuilderSpec(
        key="news",
        table="news_items",
        needs_symbol=True,
        postprocess=_pp_news,
        order_by_desc="published_at",
        limit=None,
        postprocess_kind="wrapped_dict_or_none",
        multi_strategy="special",
    ),
    EvidenceBuilderSpec(
        key="technical",
        table="technical_indicators",
        needs_symbol=True,
        postprocess=_pp_technical,
        order_by_desc="date",
        limit=2,
        postprocess_kind="dict_or_none",
        multi_strategy="max_per_symbol",
    ),
    # sector_context 特殊：needs_symbol=False（市场级），3 个独立查询
    # 调度时单独处理，不在通用调度循环内
    EvidenceBuilderSpec(
        key="sector_context",
        table="sector_daily_quote",
        needs_symbol=False,
        postprocess=_pp_sector_context,
        order_by_desc=None,
        limit=None,
        postprocess_kind="special",
        multi_strategy="special",
    ),
    # us_finance 特殊：仅 us 前缀；2 个查询（annual + quarter）
    EvidenceBuilderSpec(
        key="us_finance",
        table="us_financials",
        needs_symbol=True,
        postprocess=None,  # 特殊处理
        order_by_desc="end_date",
        limit=4,
        postprocess_kind="special",
        multi_strategy="special",
    ),
    # shareholders 特殊：跨 2 张表
    EvidenceBuilderSpec(
        key="shareholders",
        table="shareholders",
        needs_symbol=True,
        postprocess=None,
        order_by_desc="report_period, rank",
        limit=10,
        postprocess_kind="special",
        multi_strategy="special",
    ),
)

EVIDENCE_BUILDERS_BY_KEY: dict[str, EvidenceBuilderSpec] = {s.key: s for s in EVIDENCE_BUILDERS}


class EvidenceBuilder:
    @staticmethod
    def _evidence_limits() -> dict:
        """从配置文件获取证据查询的行数限制。"""
        cfg = get_config().get("evidence", {})
        return {
            "kline_limit": cfg.get("kline_limit", 60),
            "fund_flow_limit": cfg.get("fund_flow_limit", 5),
            "finance_limit": cfg.get("finance_limit", 2),
            "news_days": cfg.get("news_days", 7),
        }

    @staticmethod
    def _classify_yoy_sign(
        curr_val: float | None, prev_val: float | None
    ) -> str | None:
        """对 ``(curr_val, prev_val)`` 给出符号语义标签。

        数值同比仅看百分比会掩盖"扭亏 / 亏损收窄 / 亏损扩大"三类经济意义。
        返回值：
        - ``"turnaround"``：prev<0 且 curr>0（扭亏为盈）
        - ``"loss_narrowing"``：prev<0 且 curr<0 且 ``|curr| < |prev|``（亏损收窄）
        - ``"loss_widening"``：prev<0 且 curr<0 且 ``|curr| > |prev|``（亏损扩大）
        - ``"normal"``：其余可计算情形
        - ``None``：输入缺失或 prev=0（无法分类）

        调用方按标签调整 AI 评分口径，避免对"亏损收窄"误判为看空。
        """
        if curr_val is None or prev_val is None or prev_val == 0:
            return None
        if prev_val < 0 and curr_val > 0:
            return "turnaround"
        if prev_val < 0 and curr_val < 0:
            if abs(curr_val) < abs(prev_val):
                return "loss_narrowing"
            return "loss_widening"
        return "normal"

    @staticmethod
    def _derive_finance_yoy(rows: list[dict]) -> dict | None:
        """对 ``rows``（按 collected_at DESC 排序的最近 N 期）做 YoY/差值派生。

        派生字段：
        - ``revenue_yoy`` / ``net_profit_yoy`` / ``eps_yoy``: 百分比（最新 vs 前一期）
        - ``roe_change``: ROE 绝对差值
        - ``revenue_yoy_sign`` / ``net_profit_yoy_sign`` / ``eps_yoy_sign``:
          符号语义标签（``turnaround`` / ``loss_narrowing`` / ``loss_widening`` /
          ``normal`` / ``None``），AI 规则按标签结构化判定，避免对"扭亏"或
          "亏损收窄"误判为看空。
        - ``prev_*``: 前一期原值（向后兼容）
        - ``history``: 多期列表（按时间从旧到新）

        返回 latest 字典（已附加派生字段）；若 ``rows`` 为空则返回 ``None``。
        """
        if not rows:
            return None
        latest = dict(rows[0])
        if len(rows) >= 2:
            prev = dict(rows[1])
            for key in ("revenue", "net_profit", "eps"):
                curr_val = latest.get(key)
                prev_val = prev.get(key)
                if curr_val is not None and prev_val is not None and prev_val != 0:
                    latest[f"{key}_yoy"] = round(
                        (curr_val - prev_val) / abs(prev_val) * 100, 2
                    )
                else:
                    latest[f"{key}_yoy"] = None
                # 同步产出结构化 sign hint，便于 AIAnalyzer 按经济意义解读
                latest[f"{key}_yoy_sign"] = EvidenceBuilder._classify_yoy_sign(
                    curr_val, prev_val
                )
            if latest.get("roe") is not None and prev.get("roe") is not None:
                latest["roe_change"] = round(latest["roe"] - prev["roe"], 2)
            else:
                latest["roe_change"] = None
            latest["prev_revenue"] = prev.get("revenue")
            latest["prev_net_profit"] = prev.get("net_profit")
            latest["prev_eps"] = prev.get("eps")
            latest["prev_roe"] = prev.get("roe")
        else:
            for key in ("revenue", "net_profit", "eps"):
                latest[f"{key}_yoy"] = None
                latest[f"{key}_yoy_sign"] = None
            latest["roe_change"] = None
        latest["history"] = [dict(r) for r in reversed(rows)]
        return latest

    @staticmethod
    def _assemble_data_sources(
        quote: dict | None,
        klines: list[dict] | None,
        flows: list[dict] | None,
        finance: dict | None,
        news: dict | None,
        technical: dict | None,
        dividends: dict | None,
        shareholders: dict | None,
        forecasts: dict | None,
        sector_ctx: dict | None,
        us_finance: dict | None,
    ) -> list[dict]:
        """统一的 ``data_sources`` 装配逻辑。

        将各类型证据存在性与来源信息映射为 ``data_used`` 记录列表。
        ``build()`` 与 ``build_multi()`` 共用本 helper，确保两路径的
        ``data_used`` 字段对同一标的产出**完全等价**的元数据列表——
        这是 evidence-driven AI 约束（CLAUDE.md）所要求的：
        AI 报告声称引用的每一条数据都必须在 ``data_used`` 留痕。

        装配规则：源数据非空（``None`` / 空列表 / 空 dict）时，追加一条
        ``{type, source, collected_at}``；否则跳过。
        """
        data_sources: list[dict] = []
        if quote:
            data_sources.append(
                {
                    "type": "quote",
                    "source": quote.get("source", ""),
                    "collected_at": quote.get("collected_at", ""),
                }
            )
        if klines:
            data_sources.append(
                {
                    "type": "kline",
                    "source": klines[0].get("source", ""),
                    "collected_at": klines[0].get("collected_at", ""),
                }
            )
        if flows:
            data_sources.append(
                {
                    "type": "fund_flow",
                    "source": flows[0].get("source", ""),
                    "collected_at": flows[0].get("collected_at", ""),
                }
            )
        if finance:
            data_sources.append(
                {
                    "type": "finance",
                    "source": finance.get("source", ""),
                    "collected_at": finance.get("collected_at", ""),
                }
            )
        if news:
            data_sources.append(
                {"type": "news", "source": "news_provider", "collected_at": ""}
            )
        if technical:
            data_sources.append(
                {
                    "type": "technical",
                    "source": technical.get("source", ""),
                    "collected_at": technical.get("collected_at", ""),
                }
            )
        if dividends:
            data_sources.append(
                {
                    "type": "dividend",
                    "source": dividends.get("source", ""),
                    "collected_at": "",
                }
            )
        if shareholders:
            data_sources.append(
                {
                    "type": "shareholder",
                    "source": shareholders.get("source", ""),
                    "collected_at": "",
                }
            )
        if forecasts:
            data_sources.append(
                {
                    "type": "forecast",
                    "source": forecasts.get("source", ""),
                    "collected_at": "",
                }
            )
        if sector_ctx:
            data_sources.append(
                {
                    "type": "sector_context",
                    "source": sector_ctx.get("source", ""),
                    "collected_at": sector_ctx.get("collected_at", ""),
                }
            )
        if us_finance:
            data_sources.append(
                {
                    "type": "us_finance",
                    "source": us_finance.get("source", ""),
                    "collected_at": us_finance.get("collected_at", ""),
                }
            )
        return data_sources

    @staticmethod
    def _aggregate_news(items: list[dict]) -> dict | None:
        """对单/批标的的新闻列表做方向计数 + confidence 加权 + 板块聚合。

        输入 items 是从 news_items 表读出的字典列表（按 published_at DESC），
        每条至少包含 sentiment 字段；可选 confidence (REAL) / sectors (JSON 字符串)。

        Returns:
            完整 news 段字典；items 为空时返回 None。
        """
        if not items:
            return None

        sentiments = [item.get("sentiment", "neutral") for item in items]
        positive = sentiments.count("positive")
        negative = sentiments.count("negative")
        neutral = sentiments.count("neutral")

        # confidence 加权求和；None 视为 1.0（兼容旧数据）
        def _w(it: dict) -> float:
            c = it.get("confidence")
            return c if isinstance(c, (int, float)) else 1.0

        positive_weighted = sum(_w(it) for it in items if it.get("sentiment") == "positive")
        negative_weighted = sum(_w(it) for it in items if it.get("sentiment") == "negative")
        neutral_weighted = sum(_w(it) for it in items if it.get("sentiment") == "neutral")

        # 收集 confidence 非 None 的项算均值
        conf_values = [
            it["confidence"] for it in items
            if isinstance(it.get("confidence"), (int, float))
        ]
        avg_confidence = round(sum(conf_values) / len(conf_values), 3) if conf_values else None

        # 板块聚合：扫 sectors 列，JSON 字符串逐条解析
        sector_buckets: dict = defaultdict(
            lambda: {"count": 0, "positive": 0, "negative": 0, "neutral": 0, "_conf_sum": 0.0, "_conf_n": 0}
        )
        for it in items:
            raw = it.get("sectors")
            if not raw:
                continue
            try:
                sectors = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(sectors, list):
                continue
            sent = it.get("sentiment", "neutral")
            for s in sectors:
                if not isinstance(s, str) or not s.strip():
                    continue
                b = sector_buckets[s]
                b["count"] += 1
                if sent in ("positive", "negative", "neutral"):
                    b[sent] += 1
                c = it.get("confidence")
                if isinstance(c, (int, float)):
                    b["_conf_sum"] += c
                    b["_conf_n"] += 1

        # 板块按 count DESC，并列按板块名字典序；top 10
        sector_exposure = []
        for s in sorted(
            sector_buckets.keys(),
            key=lambda k: (-sector_buckets[k]["count"], k),
        )[:10]:
            b = sector_buckets[s]
            sector_exposure.append({
                "sector": s,
                "count": b["count"],
                "positive": b["positive"],
                "negative": b["negative"],
                "neutral": b["neutral"],
                "avg_confidence": round(b["_conf_sum"] / b["_conf_n"], 3) if b["_conf_n"] else None,
            })

        return {
            "total_count": len(items),
            "positive_count": positive,
            "negative_count": negative,
            "neutral_count": neutral,
            "positive_weighted": round(positive_weighted, 3),
            "negative_weighted": round(negative_weighted, 3),
            "neutral_weighted": round(neutral_weighted, 3),
            "avg_confidence": avg_confidence,
            "sector_exposure": sector_exposure,
            "latest": items[:5],
            "ai_scored_count": sum(1 for it in items if isinstance(it.get("confidence"), (int, float))),
        }

    # ------------------------------------------------------------------
    # 通用调度 helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_limit(spec: EvidenceBuilderSpec) -> int | None:
        """解析 spec.limit：数字直接返回，字符串（key 名）查 _evidence_limits()。"""
        if spec.limit is None:
            return None
        if isinstance(spec.limit, int):
            return spec.limit
        return EvidenceBuilder._evidence_limits()[spec.limit]

    @staticmethod
    async def _fetch_rows_single(
        conn,
        spec: EvidenceBuilderSpec,
        symbol: str | None,
        limit: int | None,
    ) -> list[dict]:
        """单标的查询：执行 SQL 返回 list[dict]。"""
        if spec.key == "news":
            limits = EvidenceBuilder._evidence_limits()
            cursor = await conn.execute(
                """SELECT * FROM news_items
                   WHERE EXISTS (SELECT 1 FROM json_each(related_symbols) WHERE value = ?)
                   AND published_at >= datetime('now', ?)
                   ORDER BY published_at DESC""",
                (symbol, f"-{limits['news_days']} days"),
            )
        elif spec.key == "sector_context":
            # 不在通用调度内（sector_context 调度由 _build_sector_context 特殊处理）
            return []
        else:
            params: tuple = (symbol,)
            sql_limit = f" LIMIT {limit}" if limit is not None else ""
            sql = f"SELECT * FROM {spec.table} WHERE symbol = ?"
            if spec.order_by_desc:
                sql += f" ORDER BY {spec.order_by_desc} DESC"
            sql += sql_limit
            cursor = await conn.execute(sql, params)
        return [dict(row) for row in await cursor.fetchall()]

    @staticmethod
    async def _fetch_rows_multi(
        conn,
        spec: EvidenceBuilderSpec,
        symbols: list[str],
        limit: int | None,
    ) -> dict[str, list[dict]]:
        """多标的批量查询：执行 WHERE IN，返回 dict[symbol, list[dict]]。

        支持两种 SQL 策略：
        - multi_strategy == "standard"：普通 WHERE IN + ORDER BY + 在 Python 端按 symbol
          累积直到每标的 limit 行
        - multi_strategy == "max_per_symbol"：用 MAX(date/collected_at) 子查询确保每标的
          取最新的 N 行（quote/technical 用，避免每标的多条历史行干扰）
        """
        if not symbols:
            return {}
        placeholders = ",".join("?" for _ in symbols)
        params = list(symbols)

        if spec.multi_strategy == "max_per_symbol":
            # 每标的最新 N 行：子查询 MAX(order_col) GROUP BY symbol,
            # 外层 WHERE order_col IN (...) 限制取最新日期的 N 行
            order_col = spec.order_by_desc or "date"
            cursor = await conn.execute(
                f"""SELECT * FROM {spec.table}
                    WHERE symbol IN ({placeholders})
                    AND {order_col} IN (
                        SELECT MAX({order_col}) FROM {spec.table}
                        WHERE symbol IN ({placeholders})
                        GROUP BY symbol
                    )""",
                params * 2,
            )
            by_symbol: dict[str, list[dict]] = {s: [] for s in symbols}
            for row in await cursor.fetchall():
                r = dict(row)
                bucket = by_symbol.get(r["symbol"])
                if bucket is not None and len(bucket) < (limit or 1):
                    bucket.append(r)
            return by_symbol

        # standard：普通 WHERE IN + ORDER BY，DESC 在 Python 端按 symbol 累积
        cursor = await conn.execute(
            f"""SELECT * FROM {spec.table}
                WHERE symbol IN ({placeholders})
                ORDER BY symbol, {spec.order_by_desc or "date"} DESC""",
            params,
        )
        by_symbol = {s: [] for s in symbols}
        for row in await cursor.fetchall():
            r = dict(row)
            bucket = by_symbol.get(r["symbol"])
            if bucket is None:
                continue
            if limit is None or len(bucket) < limit:
                bucket.append(r)
        return by_symbol

    @staticmethod
    def _build_shareholders_batch(shr_by_symbol: dict[str, dict]) -> dict[str, dict | None]:
        """清理 shareholders 双表合并后的临时字段 latest_period。"""
        for bucket in shr_by_symbol.values():
            bucket.pop("latest_period", None)
        return shr_by_symbol

    @staticmethod
    async def _build_sector_context(conn, _symbol: str | None) -> dict | None:
        """查询板块背景（行业/概念涨幅榜 Top 5 + 资金流入 Top 5）。

        不依赖具体 symbol（板块是全市场级别），但保留 symbol 参数以保持
        模板一致性。AI 报告引用大盘背景，让"今天哪些板块涨/跌"成为依据。
        """
        cursor = await conn.execute(
            """SELECT * FROM sector_daily_quote
               WHERE date = (SELECT MAX(date) FROM sector_daily_quote)
               AND sector_type IN ('industry', 'concept', 'fund_flow')
               ORDER BY change_pct DESC LIMIT 5"""
        )
        top_gainers = [dict(r) for r in await cursor.fetchall()]

        cursor = await conn.execute(
            """SELECT * FROM sector_daily_quote
               WHERE date = (SELECT MAX(date) FROM sector_daily_quote)
               AND sector_type IN ('industry', 'concept', 'fund_flow')
               ORDER BY change_pct ASC LIMIT 5"""
        )
        top_losers = [dict(r) for r in await cursor.fetchall()]

        cursor = await conn.execute(
            """SELECT * FROM sector_daily_quote
               WHERE date = (SELECT MAX(date) FROM sector_daily_quote)
               AND sector_type = 'fund_flow'
               ORDER BY main_net_inflow DESC NULLS LAST LIMIT 5"""
        )
        top_fund_inflow = [dict(r) for r in await cursor.fetchall()]

        if not top_gainers and not top_losers and not top_fund_inflow:
            return None

        source = (
            top_gainers[0].get("source")
            if top_gainers
            else (
                top_losers[0].get("source")
                if top_losers
                else (top_fund_inflow[0].get("source") if top_fund_inflow else None)
            )
        )
        collected_at = top_gainers[0].get("collected_at") if top_gainers else None

        return {
            "top_gainers": top_gainers,
            "top_losers": top_losers,
            "top_fund_inflow": top_fund_inflow,
            "source": source,
            "collected_at": collected_at,
        }

    @staticmethod
    async def _build_us_finance(conn, symbol: str) -> dict | None:
        """查询美股财务（us_financials 表，period_type=annual 最新 4 期）。"""
        cursor = await conn.execute(
            """SELECT * FROM us_financials WHERE symbol = ?
               AND period_type = 'annual'
               ORDER BY end_date DESC LIMIT 4""",
            (symbol,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        annual = [dict(r) for r in rows]

        cursor = await conn.execute(
            """SELECT * FROM us_financials WHERE symbol = ?
               AND period_type = 'quarter'
               ORDER BY end_date DESC LIMIT 4""",
            (symbol,),
        )
        quarterly = [dict(r) for r in await cursor.fetchall()]

        # 派生 YoY 增长率（最近一年 vs 去年）
        yoy = {}
        if len(annual) >= 2:
            curr = annual[0]
            prev = annual[1]
            for k in (
                "revenue",
                "net_income",
                "operating_income",
                "ebitda",
                "basic_eps",
            ):
                c, p = curr.get(k), prev.get(k)
                if c is not None and p is not None and p != 0:
                    yoy[f"{k}_yoy"] = round((c - p) / p * 100, 2)

        return {
            "annual": annual,
            "quarterly": quarterly,
            "yoy": yoy,
            "currency": annual[0].get("currency"),
            "source": annual[0].get("source"),
            "collected_at": annual[0].get("collected_at"),
        }

    @staticmethod
    async def _fetch_shareholders(conn, symbol: str) -> dict | None:
        """查询最新一期十大股东 + 股东人数趋势。"""
        # 十大股东（按报告期降序、排名升序，取最新一期前 10 名）
        cursor = await conn.execute(
            """SELECT * FROM shareholders WHERE symbol = ?
               ORDER BY report_period DESC, rank ASC LIMIT 10""",
            (symbol,),
        )
        top_rows = await cursor.fetchall()
        # 股东人数历史（最近 8 个报告期）
        cursor = await conn.execute(
            """SELECT * FROM shareholder_count_history WHERE symbol = ?
               ORDER BY report_date DESC LIMIT 8""",
            (symbol,),
        )
        count_rows = await cursor.fetchall()
        if not top_rows and not count_rows:
            return None
        return {
            "top_shareholders": [dict(r) for r in top_rows],
            "holder_count_trend": [dict(r) for r in count_rows],
            "source": (
                top_rows[0]["source"]
                if top_rows
                else (count_rows[0]["source"] if count_rows else None)
            ),
        }

    # ------------------------------------------------------------------
    # 向后兼容的 4 个 _build_* 包装方法（测试代码直接调用）
    # ------------------------------------------------------------------

    @staticmethod
    async def _build_finance(conn, symbol: str) -> dict | None:
        """多期财务 + YoY 派生指标。"""
        limits = EvidenceBuilder._evidence_limits()
        spec = EVIDENCE_BUILDERS_BY_KEY["finance"]
        rows = await EvidenceBuilder._fetch_rows_single(conn, spec, symbol, limits["finance_limit"])
        return EvidenceBuilder._derive_finance_yoy(rows)

    @staticmethod
    async def _build_dividends(conn, symbol: str) -> dict | None:
        """查询最近 4 次分红历史 + 最新一次派息（委托给注册表后处理）。"""
        spec = EVIDENCE_BUILDERS_BY_KEY["dividends"]
        rows = await EvidenceBuilder._fetch_rows_single(conn, spec, symbol, limit=4)
        return _pp_dividends(rows, symbol)

    @staticmethod
    async def _build_shareholders(conn, symbol: str) -> dict | None:
        """查询最新一期十大股东 + 股东人数趋势。"""
        return await EvidenceBuilder._fetch_shareholders(conn, symbol)

    @staticmethod
    async def _build_profit_forecasts(conn, symbol: str) -> dict | None:
        """查询最近 4 个报告期的业绩预告（委托给注册表后处理）。"""
        spec = EVIDENCE_BUILDERS_BY_KEY["forecasts"]
        rows = await EvidenceBuilder._fetch_rows_single(conn, spec, symbol, limit=4)
        return _pp_forecasts(rows, symbol)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    @staticmethod
    async def build(symbol: str, conn=None) -> dict:
        """单标的证据包构建。

        调度流程：遍历 EVIDENCE_BUILDERS 注册表，特殊项（sector_context、
        us_finance、shareholders）单独处理，其余项走通用 fetch + postprocess 链。
        """
        close_conn = conn is None
        if conn is None:
            from backend.storage.database import aget_connection
            conn = await aget_connection()

        try:
            result: dict[str, Any] = {"symbol": symbol}

            # 1) sector_context（市场级，一次性查询）
            result["sector_context"] = await EvidenceBuilder._build_sector_context(conn, symbol)

            # 2) 通用调度：遍历除 sector_context / us_finance 之外的注册表条目
            for spec in EVIDENCE_BUILDERS:
                if spec.key in ("sector_context", "us_finance"):
                    continue  # 特殊处理
                if not spec.needs_symbol:
                    continue
                if spec.key == "shareholders":
                    result["shareholders"] = await EvidenceBuilder._fetch_shareholders(conn, symbol)
                    continue
                limit = EvidenceBuilder._resolve_limit(spec)
                rows = await EvidenceBuilder._fetch_rows_single(conn, spec, symbol, limit)
                if spec.postprocess is not None:
                    result[spec.key] = spec.postprocess(rows, symbol)
                else:
                    result[spec.key] = rows

            # 3) us_finance：仅 us 前缀
            if symbol.startswith("us"):
                result["us_finance"] = await EvidenceBuilder._build_us_finance(conn, symbol)
            else:
                result["us_finance"] = None

            result["data_sources"] = EvidenceBuilder._assemble_data_sources(
                result.get("quote"),
                result.get("kline"),
                result.get("fund_flows"),
                result.get("finance"),
                result.get("news"),
                result.get("technical"),
                result.get("dividends"),
                result.get("shareholders"),
                result.get("forecasts"),
                result.get("sector_context"),
                result.get("us_finance"),
            )
            return result
        finally:
            if close_conn:
                with suppress(Exception):
                    await conn.close()

    @staticmethod
    async def build_multi(symbols: list[str]) -> dict[str, dict]:
        """批量构建多个标的的证据包，用 WHERE IN 减少查询次数。

        调度流程（与 build() 对齐）：
        1. 遍历 EVIDENCE_BUILDERS 注册表，区分策略：
           - multi_strategy == "standard" -> 通用 _fetch_rows_multi（每标的累积 limit 行）
           - multi_strategy == "max_per_symbol" -> MAX 子查询（quote / technical）
           - multi_strategy == "special" -> 调用专用 _build_* 方法
        2. news 一次性拉 7 天窗口，Python 端按 related_symbols 分桶
        3. sector_context 跨标的共享一次查询
        4. us_finance 仅 us 前缀
        5. shareholders 跨 2 张表
        6. 组装每标的 result（与 build() 共享 postprocess）
        """
        if not symbols:
            return {}
        from backend.storage.database import aget_connection

        conn = await aget_connection()
        try:
            # ---------- 阶段 1: 注册表通用批量查询 ----------
            by_symbol_data: dict[str, dict[str, list[dict] | dict | None]] = {
                s: {} for s in symbols
            }

            for spec in EVIDENCE_BUILDERS:
                if spec.multi_strategy == "special":
                    continue  # sector_context / us_finance / shareholders / news 单独处理
                limit = EvidenceBuilder._resolve_limit(spec)
                rows_by_sym = await EvidenceBuilder._fetch_rows_multi(
                    conn, spec, symbols, limit
                )
                for sym in symbols:
                    by_symbol_data[sym][spec.key] = rows_by_sym.get(sym, [])

            # ---------- 阶段 2: 特殊项 ----------
            # news: 一次性拉 7 天窗口，Python 端按 related_symbols 分桶
            cursor = await conn.execute(
                """SELECT * FROM news_items
                   WHERE published_at >= datetime("now", "-7 days")
                   ORDER BY published_at DESC
                   LIMIT 5001""",
            )
            all_news_rows: list[dict] = [dict(r) for r in await cursor.fetchall()]
            if len(all_news_rows) > 5000:
                logger.warning(
                    "build_multi: news_items 命中 LIMIT 5000 截断,共 {} 行可能未参与评分",
                    len(all_news_rows) - 5000,
                )
                all_news_rows = all_news_rows[:5000]
            news_by_symbol: dict[str, list[dict]] = {sym: [] for sym in symbols}
            for row in all_news_rows:
                related_raw = row.get("related_symbols")
                if not related_raw:
                    continue
                try:
                    related = (
                        json.loads(related_raw)
                        if isinstance(related_raw, str)
                        else related_raw
                    )
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(related, list):
                    continue
                for sym in related:
                    bucket = news_by_symbol.get(sym)
                    if bucket is not None and len(bucket) < 100:
                        bucket.append(row)
            for sym in symbols:
                by_symbol_data[sym]["news"] = news_by_symbol.get(sym, [])

            # shareholders: 跨 2 张表
            shr_by_symbol: dict[str, dict] = {}
            placeholders = ",".join("?" for _ in symbols)
            params = list(symbols)
            cursor = await conn.execute(
                f"""SELECT * FROM shareholders
                    WHERE symbol IN ({placeholders})
                    ORDER BY symbol, report_period DESC, rank ASC""",
                params,
            )
            for row in await cursor.fetchall():
                r = dict(row)
                sym = r["symbol"]
                bucket = shr_by_symbol.get(sym)
                if bucket is None:
                    bucket = {
                        "top_shareholders": [],
                        "latest_period": r["report_period"],
                        "source": r.get("source"),
                    }
                    shr_by_symbol[sym] = bucket
                if r["report_period"] != bucket["latest_period"]:
                    continue
                if len(bucket["top_shareholders"]) < 10:
                    bucket["top_shareholders"].append(r)
            cursor = await conn.execute(
                f"""SELECT * FROM shareholder_count_history
                    WHERE symbol IN ({placeholders})
                    ORDER BY symbol, report_date DESC""",
                params,
            )
            for row in await cursor.fetchall():
                r = dict(row)
                sym = r["symbol"]
                bucket = shr_by_symbol.setdefault(
                    sym,
                    {"top_shareholders": [], "source": r.get("source")},
                )
                bucket.setdefault("holder_count_trend", [])
                if len(bucket["holder_count_trend"]) < 8:
                    bucket["holder_count_trend"].append(r)
                if not bucket.get("source"):
                    bucket["source"] = r.get("source")
            EvidenceBuilder._build_shareholders_batch(shr_by_symbol)
            for sym in symbols:
                by_symbol_data[sym]["shareholders_raw"] = shr_by_symbol.get(sym)

            # sector_context 共享一次查询
            sector_ctx_shared = await EvidenceBuilder._build_sector_context(
                conn, symbols[0]
            )

            # us_finance 仅 us 前缀
            us_symbols = [s for s in symbols if s.startswith("us")]
            us_finance_map: dict[str, dict | None] = {}
            for s in us_symbols:
                us_finance_map[s] = await EvidenceBuilder._build_us_finance(conn, s)

            # ---------- 阶段 3: 注册表驱动组装（与 build() 共享 postprocess） ----------
            result: dict[str, dict] = {}
            for symbol in symbols:
                by_spec_rows = by_symbol_data[symbol]
                evidence: dict = {"symbol": symbol}

                # 通用 spec：调 postprocess
                for spec in EVIDENCE_BUILDERS:
                    if spec.multi_strategy == "special":
                        continue
                    if spec.postprocess is None:
                        evidence[spec.key] = by_spec_rows.get(spec.key, [])
                    else:
                        evidence[spec.key] = spec.postprocess(
                            by_spec_rows.get(spec.key, []), symbol
                        )

                # shareholders: 来自双表 bucket
                shr_bucket = by_spec_rows.get("shareholders_raw")
                if shr_bucket and (
                    shr_bucket.get("top_shareholders")
                    or shr_bucket.get("holder_count_trend")
                ):
                    evidence["shareholders"] = {
                        "top_shareholders": shr_bucket.get("top_shareholders", []),
                        "holder_count_trend": shr_bucket.get("holder_count_trend", []),
                        "source": shr_bucket.get("source"),
                    }
                else:
                    evidence["shareholders"] = None

                # sector_context 共享
                evidence["sector_context"] = sector_ctx_shared

                # us_finance 仅 us 前缀；非 us 标的固定 None
                evidence["us_finance"] = us_finance_map.get(symbol)

                evidence["data_sources"] = EvidenceBuilder._assemble_data_sources(
                    evidence.get("quote"),
                    evidence.get("kline"),
                    evidence.get("fund_flows"),
                    evidence.get("finance"),
                    evidence.get("news"),
                    evidence.get("technical"),
                    evidence.get("dividends"),
                    evidence.get("shareholders"),
                    evidence.get("forecasts"),
                    evidence.get("sector_context"),
                    evidence.get("us_finance"),
                )
                result[symbol] = evidence
            return result
        finally:
            with suppress(Exception):
                await conn.close()
