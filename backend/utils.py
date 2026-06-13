"""MarketLens 通用工具函数。"""

import re


def escape_like(value: str, escape_char: str = "\\") -> str:
    """转义 SQLite LIKE 查询中的特殊字符 % 和 _。

    Args:
        value: 需要转义的原始字符串。
        escape_char: 转义字符，默认反斜杠。

    Returns:
        转义后的字符串。
    """
    return (
        value.replace(escape_char, escape_char * 2)
        .replace("%", f"{escape_char}%")
        .replace("_", f"{escape_char}_")
    )


def try_parse_float(value: object, *, extra_strip: str = "") -> float | None:
    """安全解析数字字符串为 float，失败返回 None。

    默认剥离千分位逗号、Tab / 换行 / 普通空白；``extra_strip`` 可追加剥离
    字符(典型用法: ``extra_strip="%亿万元"`` 剥离中文金额单位与百分号)。

    边界:
        - ``None`` / 空串 / ``"-"`` → ``None``
        - ``int`` / ``float`` 直接返回 ``float(value)``
        - 数字字符串(支持 ``"1,234.56"`` / ``"-28.80"`` / ``"3.5亿"``) → 对应 float
        - 解析失败 → ``None``(不抛异常)

    合并自 ``SinaProvider._safe_float``(原剥离 ``,`` + 空白)与
    ``NeoDataProvider._try_float``(原剥离 ``,%亿万元``),两处实现语义对齐
    后由本函数统一提供。
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    pattern = rf"[,\s{re.escape(extra_strip)}]" if extra_strip else r"[,\s]"
    cleaned = re.sub(pattern, "", str(value))
    if not cleaned or cleaned == "-":
        return None
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def build_fund_flow_summary(fund_rows: list[dict]) -> dict | None:
    """构建资金流向摘要。

    Args:
        fund_rows: 资金流向数据行列表（按日期倒序），每行需含 main_net_inflow 字段，
                   可选 net_inflow_ratio 字段。支持 sqlite3.Row 和 dict 两种行类型。

    Returns:
        包含 net_flow_5d、trend、avg_net_inflow_ratio 的摘要字典，无数据时返回 None。
    """
    if not fund_rows:
        return None

    net_flow_5d = sum(row["main_net_inflow"] or 0 for row in fund_rows)

    # 统计连续净流入/流出（从最早到最新，按日检测连续天数）
    inflows = 0
    outflows = 0
    for row in reversed(fund_rows):
        val = row["main_net_inflow"] or 0
        if val > 0:
            inflows += 1
            outflows = 0
        elif val < 0:
            outflows += 1
            inflows = 0
        else:
            inflows = 0
            outflows = 0

    if inflows >= 3:
        trend = f"连续 {inflows} 日净流入"
    elif outflows >= 3:
        trend = f"连续 {outflows} 日净流出"
    else:
        trend = f"近 {len(fund_rows)} 日资金流向交替"

    # 净流入占比均值（仅当数据包含 net_inflow_ratio 列时计算）
    raw_ratios: list[float] = []
    for row in fund_rows:
        # sqlite3.Row 不支持 .get()，使用 keys() 检测列是否存在
        if "net_inflow_ratio" not in row.keys():
            break
        val = row["net_inflow_ratio"]
        if val is not None:
            raw_ratios.append(val)
    avg_ratio = sum(raw_ratios) / len(raw_ratios) if raw_ratios else 0.0

    return {
        "net_flow_5d": net_flow_5d,
        "trend": trend,
        "avg_net_inflow_ratio": round(avg_ratio, 2),
    }
