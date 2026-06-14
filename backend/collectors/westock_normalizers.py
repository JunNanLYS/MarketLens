"""WeStock 数据归一化（标准化）函数集合。

原 WeStockProvider 类的 24 个 _normalize_* 方法 + 2 个 helper 全部提取到本文件，
从实例方法变成纯函数（仅依赖 _try_number + 显式 collected_at 参数）。
调用方 WeStockProvider 通过类属性重导出保持向后兼容。
"""

import json

# 行情市场前缀：A 股 / 港股 / 美股 / 港股通 等
_A_SHARE_PREFIXES: tuple[str, ...] = ("sh", "sz", "bj")


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



def _normalize_quote(raw: dict, symbol: str, collected_at: str) -> dict:
    last_val = _try_number(raw.get("last", ""))
    open_val = _try_number(raw.get("open", ""))
    prev_close = _try_number(
        raw.get("prev_close", raw.get("pre_close", raw.get("settlement")))
    )
    if prev_close is None:
        change_val = _try_number(raw.get("change", raw.get("chg", "")))
        if isinstance(last_val, (int, float)) and isinstance(
            change_val, (int, float)
        ):
            prev_close = last_val - change_val
    change = None
    if isinstance(prev_close, (int, float)) and isinstance(last_val, (int, float)):
        change = last_val - prev_close
    return {
        "symbol": symbol,
        "price": last_val if isinstance(last_val, (int, float)) else None,
        "change": change,
        "change_pct": _try_number(
            raw.get("percent", raw.get("chg_rate", raw.get("涨跌幅")))
        ),
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
        "collected_at": collected_at,
    }



def _normalize_kline(raw: dict, symbol: str, collected_at: str) -> dict:
    return {
        "symbol": symbol,
        "date": raw.get("date", ""),
        "open": _try_number(raw.get("open", "")),
        "high": _try_number(raw.get("high", "")),
        "low": _try_number(raw.get("low", "")),
        "close": _try_number(raw.get("last", "")),
        "volume": _try_number(raw.get("volume", "")),
        "amount": _try_number(raw.get("amount", "")),
        "change_pct": _try_number(
            raw.get("percent", raw.get("chg_rate", raw.get("涨跌幅")))
        ),
        "source": "westock",
        "collected_at": collected_at,
    }



def _normalize_finance(tables: list[list[dict[str, str]]], symbol: str, collected_at: str) -> dict:
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
    if (
        revenue
        and isinstance(revenue, (int, float))
        and net_profit
        and isinstance(net_profit, (int, float))
    ):
        net_margin = round(net_profit / revenue * 100, 2)

    roe = None
    if (
        net_profit
        and isinstance(net_profit, (int, float))
        and se_wo_mi
        and isinstance(se_wo_mi, (int, float))
    ):
        roe = round(net_profit / se_wo_mi * 100, 2)

    debt_ratio = None
    if (
        total_assets
        and isinstance(total_assets, (int, float))
        and total_liability
        and isinstance(total_liability, (int, float))
    ):
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
        "collected_at": collected_at,
    }



def _normalize_fund_flow(raw: dict, symbol: str, collected_at: str) -> dict:
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
        "collected_at": collected_at,
    }



def _normalize_technical(raw: dict, symbol: str, collected_at: str) -> dict:
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
        "collected_at": collected_at,
    }



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



def _normalize_minute_row(raw: dict, symbol: str, collected_at: str) -> dict:
    return {
        "symbol": symbol,
        "time": raw.get("time", ""),
        "price": _try_number(raw.get("price", "")),
        "volume": _try_number(raw.get("volume", "")),
        "avg_price": _try_number(raw.get("avg_price", "")),
        "source": "westock",
        "collected_at": collected_at,
    }



def _normalize_dividend(raw: dict, symbol: str, collected_at: str) -> dict:
    return {
        "symbol": symbol,
        "ex_date": raw.get("ex_date", raw.get("ex_dividend_date", "")),
        "cash_dividend": _try_number(
            raw.get("cash_dividend", raw.get("CashDiv", ""))
        ),
        "share_bonus": _try_number(
            raw.get("share_bonus", raw.get("BonusShareRatio", ""))
        ),
        "record_date": raw.get("record_date", raw.get("recordDate", "")),
        "announce_date": raw.get("announce_date", raw.get("announceDate", "")),
        "dividend_year": raw.get("dividend_year", raw.get("year", "")),
        "source": "westock",
        "collected_at": collected_at,
    }



def _normalize_shareholder(tables: list[list[dict[str, str]]], symbol: str, collected_at: str) -> dict:
    result: dict = {
        "symbol": symbol,
        "source": "westock",
        "collected_at": collected_at,
    }
    share_holders: list[dict] = []
    if tables and tables[0]:
        for row in tables[0]:
            share_holders.append(
                {
                    "rank": _try_number(row.get("rank", row.get("HolderRank", ""))),
                    "name": row.get("name", row.get("HolderName", "")),
                    "shares": _try_number(
                        row.get("shares", row.get("HoldAmount", ""))
                    ),
                    "ratio": _try_number(
                        row.get("ratio", row.get("HoldPercent", ""))
                    ),
                    "change": _try_number(row.get("change", row.get("Change", ""))),
                }
            )
    result["top_shareholders"] = share_holders

    holder_count: list[dict] = []
    if len(tables) >= 2 and tables[1]:
        for row in tables[1]:
            holder_count.append(
                {
                    "date": row.get("date", row.get("EndDate", "")),
                    "total_holders": _try_number(
                        row.get("total_holders", row.get("HolderTotal", ""))
                    ),
                    "avg_shares": _try_number(
                        row.get("avg_shares", row.get("AvgShares", ""))
                    ),
                }
            )
    result["holder_count_history"] = holder_count
    return result



def _normalize_reserve(tables: list[list[dict[str, str]]], symbol: str, collected_at: str) -> dict:
    if not tables or not tables[0]:
        return {
            "symbol": symbol,
            "source": "westock",
            "collected_at": collected_at,
        }
    row = tables[0][0]
    return {
        "symbol": symbol,
        "report_period": row.get("report_period", row.get("ReportDate", "")),
        "forecast_type": row.get("forecast_type", row.get("ForcastType", "")),
        "profit_lower": _try_number(
            row.get("profit_lower", row.get("NetProfitLow", ""))
        ),
        "profit_upper": _try_number(
            row.get("profit_upper", row.get("NetProfitHigh", ""))
        ),
        "change_lower": _try_number(
            row.get("change_lower", row.get("ChangeLow", ""))
        ),
        "change_upper": _try_number(
            row.get("change_upper", row.get("ChangeHigh", ""))
        ),
        "summary": row.get("summary", row.get("Summary", "")),
        "source": "westock",
        "collected_at": collected_at,
    }

# ------------------------------------------------------------------
# 阶段 14：ETF 全套（5 个方法 + 5 个 _normalize）
# westock CLI: etf / etf-holdings / etf-nav / etf-holders / etf-financial
# ------------------------------------------------------------------



def _normalize_etf_info(raw: dict, symbol: str, collected_at: str) -> dict:
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
        "collected_at": collected_at,
    }



def _normalize_etf_holding_row(raw: dict, symbol: str, collected_at: str) -> dict:
    return {
        "symbol": symbol,
        "constituent_code": raw.get("code", ""),
        "constituent_name": raw.get("name", ""),
        "ratio": _try_number(raw.get("ratio", "")),
        "date": raw.get("date", ""),
        "source": "westock",
        "collected_at": collected_at,
    }



def _normalize_etf_nav_row(raw: dict, symbol: str, collected_at: str) -> dict:
    return {
        "symbol": symbol,
        "date": raw.get("date", ""),
        "nav": _try_number(raw.get("nav", "")),
        "nav_change": _try_number(raw.get("navChange", "")),
        "nav_change_pct": _try_number(raw.get("navChangePct", "")),
        "acc_nav": _try_number(raw.get("accNav", "")),
        "source": "westock",
        "collected_at": collected_at,
    }



def _normalize_etf_holders(raw: dict, symbol: str, collected_at: str) -> dict:
    return {
        "symbol": symbol,
        "report_date": raw.get("date", ""),
        "holder_account": _try_number(raw.get("holderAccount", "")),
        "individual_holder_share": _try_number(
            raw.get("individualHolderShare", "")
        ),
        "individual_holder_ratio": _try_number(
            raw.get("individualHolderRatio", "")
        ),
        "institution_holder_share": _try_number(
            raw.get("institutionHolderShare", "")
        ),
        "institution_holder_ratio": _try_number(
            raw.get("institutionHolderRatio", "")
        ),
        "top10_share": _try_number(raw.get("top10Share", "")),
        "top10_ratio": _try_number(raw.get("top10Ratio", "")),
        "source": "westock",
        "collected_at": collected_at,
    }



def _normalize_etf_financial(raw: dict, symbol: str, collected_at: str) -> dict:
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
        "collected_at": collected_at,
    }

# ------------------------------------------------------------------
# 阶段 8 修正：板块首页 (board) + 热门板块 (hot board)
# ------------------------------------------------------------------



def _normalize_board_sector_row(raw: dict, sector_type: str, collected_at: str) -> dict:
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
        "collected_at": collected_at,
    }



def _normalize_hot_sector_row(raw: dict, collected_at: str) -> dict:
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
        "collected_at": collected_at,
    }

# ------------------------------------------------------------------
# 阶段 15：港美股财务（us_finance / hk_finance）
# westock CLI:
#   - finance usAAPL                  → 默认 3 表 (income/balance/cashflow)
#   - finance hk00700 --type zhsy     → 综合损益表
#   - finance hk00700 --type zcfz     → 资产负债表
#   - finance hk00700 --type xjll     → 现金流量表
# ------------------------------------------------------------------



def _normalize_us_finance_row(raw: dict, symbol: str, ftype: str, collected_at: str) -> dict:
    # 区分季度（_Q 后缀）和年度（无后缀）
    period_type = (
        "quarter"
        if any(str(k).endswith("_Q") for k in raw.keys() if k != "SecuCode")
        else "annual"
    )
    # 优先取 EndDate，否则用 _date
    end_date = raw.get("EndDate", "") or raw.get("_date", "")
    # 选对应周期的字段（季度优先 _Q 后缀，年度无后缀）
    suffix = "_Q" if period_type == "quarter" else ""
    # period_mark 例: "2024Q1" / "2024FY"
    end_str = str(end_date)
    if end_str and len(end_str) >= 10:
        year = end_str[:4]
        month = end_str[5:7]
        period_mark = (
            f"{year}Q{(int(month) - 1) // 3 + 1}"
            if period_type == "quarter"
            else f"{year}FY"
        )
    else:
        period_mark = ""

    def _n(*keys: str) -> float | None:
        for k in keys:
            v = raw.get(k)
            if v is not None and v != "" and v != "-":
                return _try_number(v)
        return None

    return {
        "symbol": symbol,
        "end_date": str(end_date)[:10] if end_date else "",
        "period_type": period_type,
        "currency": "USD",
        "period_mark": period_mark,
        # 利润表
        "revenue": _n(f"Sales{suffix}", "Sales"),
        "net_income": _n(f"NetIncome{suffix}", "NetIncome"),
        "gross_profit": _n(f"GrossIncome{suffix}", "GrossIncome"),
        "operating_income": _n(f"OperatingIncome{suffix}", "OperatingIncome"),
        "ebitda": _n(f"EBITDA{suffix}", "EBITDA"),
        "ebit": _n(f"EBIT{suffix}", "EBIT"),
        "basic_eps": _n(f"BasicEPS{suffix}", "BasicEPS"),
        "diluted_eps": _n(f"DilutedEPS{suffix}", "DilutedEPS"),
        # 资产负债表
        "total_assets": _n("TotalAssets"),
        "total_liabilities": _n("TotalLiabilities"),
        "total_equity": _n("TotalEquity", "TotalShareholderEquity"),
        # 现金流表
        "operating_cashflow": _n(f"CFO{suffix}", "CFO"),
        "investing_cashflow": _n(f"CFI{suffix}", "CFI"),
        "financing_cashflow": _n(f"CFF{suffix}", "CFF"),
        "capex": _n(f"Capex{suffix}", "Capex"),
        "raw_json": str(raw),
        "source": "westock",
        "collected_at": collected_at,
    }



def _normalize_hk_finance_row(raw: dict, symbol: str, ftype: str, collected_at: str) -> dict:
    # 港股 zhsy 表字段例: BasicEPS / OperatingIncome / OperatingProfit /
    #  NetAssetPS / ProfitToShareholders / OperatingIncome / ...
    # zcfz 表字段例: TotalAssets / TotalLiability / SEWithoutMI / ...
    # xjll 表字段例: NetOperateCashFlow / NetInvestCashFlow /
    #  NetFinanceCashFlow / ...
    period_type = (
        "quarter"
        if raw.get("ReportType") in ("第一季报", "中报", "第三季报")
        else "annual"
    )
    end_date = raw.get("EndDate", "") or raw.get("_date", "")
    end_str = str(end_date)
    if end_str and len(end_str) >= 10:
        year = end_str[:4]
        report_type = raw.get("ReportType", "")
        if report_type == "第一季报":
            period_mark = f"{year}Q1"
        elif report_type == "中报":
            period_mark = f"{year}Q2"
        elif report_type == "第三季报":
            period_mark = f"{year}Q3"
        else:
            period_mark = f"{year}FY"
    else:
        period_mark = ""

    def _n(*keys: str) -> float | None:
        for k in keys:
            v = raw.get(k)
            if v is not None and v != "" and v != "-":
                return _try_number(v)
        return None

    return {
        "symbol": symbol,
        "end_date": str(end_date)[:10] if end_date else "",
        "period_type": period_type,
        "currency": "HKD",
        "period_mark": period_mark,
        # 利润表核心
        "revenue": _n("OperatingRevenue", "OperatingRevenueTTM"),
        "net_income": _n("ProfitToShareholders", "NPParentCompanyOwners"),
        "gross_profit": _n("GrossProfit", "GrossProfitTTM"),
        "operating_income": _n("OperatingIncome", "OperatingProfit"),
        "ebitda": _n("EBITDA"),
        "ebit": _n("EBIT"),
        "basic_eps": _n("BasicEPS"),
        "diluted_eps": _n("DilutedEPS"),
        # 资产负债表核心
        "total_assets": _n("TotalAssets"),
        "total_liabilities": _n("TotalLiability"),
        "total_equity": _n("SEWithoutMI", "TotalShareholderEquity"),
        # 现金流表核心
        "operating_cashflow": _n("NetOperateCashFlow"),
        "investing_cashflow": _n("NetInvestCashFlow"),
        "financing_cashflow": _n("NetFinanceCashFlow"),
        "capex": _n("Capex"),
        "raw_json": str(raw),
        "source": "westock",
        "collected_at": collected_at,
    }

# ------------------------------------------------------------------
# 阶段 16：港美 IPO + exdiv 日历
# westock CLI:
#   - ipo hk / ipo us                        → 新股日历
#   - exdiv hk<sym> / exdiv us<sym>         → 除权日历
# A 股 ipo / exdiv 数据源死，不接
# ------------------------------------------------------------------



def _normalize_ipo_row(raw: dict, market: str, collected_at: str) -> dict:
    """ipo 输出: stage / code / name / price / sgrq / ssrq / hy。
    美股 IPO 输出列名是 status 而非 stage（兼容两种）。
    """
    # event_date 优先 sgrq（申购日），无则 listingDate（美股），最后 ssrq
    event_date = (
        raw.get("sgrq", "") or raw.get("listingDate", "") or raw.get("ssrq", "")
    )
    return {
        "event_type": "ipo",
        "event_date": event_date,
        "symbol": raw.get("code", ""),
        "name": raw.get("name", ""),
        "market": market,
        "stage": raw.get("stage") or raw.get("status", ""),
        "price": _try_number(raw.get("price")),
        "listing_date": raw.get("ssrq", "") or raw.get("listingDate", ""),
        "sgrq": raw.get("sgrq", ""),
        "ssrq": raw.get("ssrq", ""),
        "ex_div_date": None,
        "pay_date": None,
        "report_end_date": None,
        "dividend_per_share": None,
        "currency": None,
        "dividend_plan": None,
        "source": "westock",
        "collected_at": collected_at,
    }



def _normalize_exdiv_row(raw: dict, symbol: str, collected_at: str) -> dict:
    """exdiv 输出: code / name / exDivDate / payDate / reportEndDate /
    dividendPerShare / currency / dividendPlan。"""
    sym = raw.get("code", "") or symbol
    name = raw.get("name", "")
    # 与同文件 _fund_flow_cmd 保持一致：基于 symbol[:2] 前缀推断市场
    prefix = sym[:2].lower()
    market = prefix if prefix in ("hk", "us") else ""
    return {
        "event_type": "exdiv",
        "event_date": raw.get("exDivDate", ""),
        "symbol": sym,
        "name": name,
        "market": market,
        "stage": None,
        "price": None,
        "listing_date": None,
        "sgrq": None,
        "ssrq": None,
        "ex_div_date": raw.get("exDivDate", ""),
        "pay_date": raw.get("payDate", ""),
        "report_end_date": raw.get("reportEndDate", ""),
        "dividend_per_share": _try_number(raw.get("dividendPerShare")),
        "currency": raw.get("currency", ""),
        "dividend_plan": raw.get("dividendPlan", ""),
        "source": "westock",
        "collected_at": collected_at,
    }

# ------------------------------------------------------------------
# 阶段 17：筹码 / 融资融券 / 大宗 / 龙虎榜
# westock CLI:
#   - chip sh600519         → 筹码成本（仅 A 股）
#   - margintrade sh600519  → 融资融券（仅 A 股）
#   - blocktrade sh600519 --date 2026-06-01 → 大宗交易（仅 A 股，需日期）
#   - lhb sh600519 --date 2026-06-01       → 龙虎榜（仅 A 股，需日期）
# ------------------------------------------------------------------



def _normalize_chip_row(raw: dict, symbol: str, collected_at: str) -> dict:
    """chip 输出: code/name/date/closePrice/chipProfitRate/chipAvgCost/
    chipConcentration90/chipConcentration70。"""
    return {
        "symbol": symbol,
        "date": raw.get("date", ""),
        "close_price": _try_number(raw.get("closePrice")),
        "chip_profit_rate": _try_number(raw.get("chipProfitRate")),
        "chip_avg_cost": _try_number(raw.get("chipAvgCost")),
        "chip_concentration_90": _try_number(raw.get("chipConcentration90")),
        "chip_concentration_70": _try_number(raw.get("chipConcentration70")),
        "source": "westock",
        "collected_at": collected_at,
    }



def _normalize_margintrade_row(raw: dict, symbol: str, collected_at: str) -> dict:
    """margintrade 输出: code/name/date/closePrice/changePct/FinanceValue/
    SecurityValue/FinanceBuyValue/FinanceRefundValue/TradingValue/
    TradingValueDif/FinanceValueDOD/SecurityValueDOD。"""
    return {
        "symbol": symbol,
        "date": raw.get("date", ""),
        "close_price": _try_number(raw.get("closePrice")),
        "change_pct": _try_number(raw.get("changePct")),
        "finance_value": _try_number(raw.get("FinanceValue")),
        "security_value": _try_number(raw.get("SecurityValue")),
        "finance_buy_value": _try_number(raw.get("FinanceBuyValue")),
        "finance_refund_value": _try_number(raw.get("FinanceRefundValue")),
        "trading_value": _try_number(raw.get("TradingValue")),
        "trading_value_dif": _try_number(raw.get("TradingValueDif")),
        "finance_value_dod": _try_number(raw.get("FinanceValueDOD")),
        "security_value_dod": _try_number(raw.get("SecurityValueDOD")),
        "source": "westock",
        "collected_at": collected_at,
    }



def _normalize_blocktrade_row(tables: list[list[dict[str, str]]], symbol: str, date: str, collected_at: str) -> dict:
    """大宗交易归一化。

    概览来自 tables[0][0]（closePrice / changePct）。明细来自 tables[1]：
    westock CLI 在表 2 输出每笔成交（成交价 / 成交额 / 折溢率 / 买卖方向 / 营业部）。
    buy_department / sell_department 列以 JSON 列表存多条记录（同一 (symbol, date)
    可对应多笔大宗交易）；turnover_value 取合计，turnover_price / close_discount_rate
    取首笔以保持稳定性。tables[1] 缺失或列名不匹配时回落 None（向后兼容老 CLI 输出）。
    """
    overview = tables[0][0] if tables and tables[0] else {}
    detail_rows = _extract_detail_rows(tables, skip_first=True)
    # 汇总明细（多笔合并）
    turnover_value: float | None = None
    turnover_price: float | None = None
    close_discount_rate: float | None = None
    buy_departments: list[str] = []
    sell_departments: list[str] = []
    for row in detail_rows:
        tv = _try_number(
            row.get("turnoverValue")
            or row.get("成交金额")
            or row.get("amount")
            or ""
        )
        if isinstance(tv, (int, float)):
            turnover_value = (turnover_value or 0) + float(tv)
        tp_raw = (
            row.get("turnoverPrice")
            or row.get("成交价格")
            or row.get("price")
            or ""
        )
        tp = _try_number(tp_raw)
        if isinstance(tp, (int, float)) and turnover_price is None:
            turnover_price = float(tp)
        dr_raw = (
            row.get("discountRate")
            or row.get("closeDiscountRate")
            or row.get("折溢率")
            or ""
        )
        dr = _try_number(dr_raw)
        if isinstance(dr, (int, float)) and close_discount_rate is None:
            close_discount_rate = float(dr)
        # 营业部：多种列名兼容 + 通过 tradingType / direction 区分买卖方向
        dept = (
            row.get("buySalesDepartment")
            or row.get("营业部")
            or row.get("department")
            or ""
        ).strip()
        direction = (
            row.get("tradingType")
            or row.get("direction")
            or row.get("买卖方向")
            or ""
        ).strip()
        if not dept:
            continue
        # 方向判断：包含 "买"/"buy"/"BUY" 视为买方；包含 "卖"/"sell"/"SELL" 视为卖方；
        # 缺失方向时归入买方（保守）
        d_lower = direction.lower()
        if "卖" in direction or "sell" in d_lower:
            sell_departments.append(dept)
        else:
            buy_departments.append(dept)
    return {
        "symbol": symbol,
        "date": date,
        "close_price": _try_number(overview.get("closePrice")),
        "change_pct": _try_number(overview.get("changePct")),
        "turnover_price": turnover_price,
        "turnover_value": turnover_value,
        "close_discount_rate": close_discount_rate,
        "buy_department": json.dumps(buy_departments, ensure_ascii=False)
        if buy_departments
        else None,
        "sell_department": json.dumps(sell_departments, ensure_ascii=False)
        if sell_departments
        else None,
        "source": "westock",
        "collected_at": collected_at,
    }



def _normalize_lhb_row(tables: list[list[dict[str, str]]], symbol: str, date: str, collected_at: str) -> dict:
    """龙虎榜归一化。

    概览来自 tables[0][0]（closePrice / changePct / netBuyAmount）。
    明细来自 tables[1]：营业部买卖明细（多行）；营业部名称以 JSON 列表
    存于 buy_department / sell_department TEXT 列。tables[1] 缺失或列名
    不匹配时回落 None（向后兼容老 CLI 输出）。
    """
    overview = tables[0][0] if tables and tables[0] else {}
    detail_rows = _extract_detail_rows(tables, skip_first=True)
    buy_departments: list[str] = []
    sell_departments: list[str] = []
    for row in detail_rows:
        # 兼容多种列名
        dept = (
            row.get("buySalesDepartment")
            or row.get("营业部")
            or row.get("department")
            or row.get("name")
            or ""
        ).strip()
        direction = (
            row.get("tradingType")
            or row.get("direction")
            or row.get("买卖方向")
            or row.get("side")
            or ""
        ).strip()
        if not dept:
            continue
        d_lower = direction.lower()
        if "卖" in direction or "sell" in d_lower:
            sell_departments.append(dept)
        elif "买" in direction or "buy" in d_lower:
            buy_departments.append(dept)
        else:
            # 方向不明：尝试从 amount 正负判断
            amt = _try_number(
                row.get("buyAmount") or row.get("amount") or row.get("金额") or ""
            )
            if isinstance(amt, (int, float)):
                if amt >= 0:
                    buy_departments.append(dept)
                else:
                    sell_departments.append(dept)
            else:
                buy_departments.append(dept)
    return {
        "symbol": symbol,
        "date": date,
        "name": overview.get("name", ""),
        "close_price": _try_number(overview.get("closePrice")),
        "change_pct": _try_number(overview.get("changePct")),
        "net_buy_amount": _try_number(overview.get("netBuyAmount")),
        "buy_department": json.dumps(buy_departments, ensure_ascii=False)
        if buy_departments
        else None,
        "sell_department": json.dumps(sell_departments, ensure_ascii=False)
        if sell_departments
        else None,
        "reason": overview.get("reason", ""),
        "source": "westock",
        "collected_at": collected_at,
    }



def _extract_detail_rows(
    tables: list[list[dict[str, str]]], *, skip_first: bool
) -> list[dict[str, str]]:
    """从多张 markdown 表汇总明细行。

    默认跳过 tables[0]（概览表），返回 tables[1:] 全部行。
    兼容某些 CLI 把明细放在 tables[0] 后续行的情况（skip_first=False）。
    """
    rows: list[dict[str, str]] = []
    if not tables:
        return rows
    start = 1 if skip_first else 0
    for tbl in tables[start:]:
        rows.extend(tbl)
    return rows


