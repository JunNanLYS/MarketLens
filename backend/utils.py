def escape_like(value: str, escape_char: str = "\\") -> str:
    return value.replace(escape_char, escape_char * 2).replace("%", f"{escape_char}%").replace("_", f"{escape_char}_")

def build_fund_flow_summary(fund_rows: list[dict]) -> dict | None:
    if not fund_rows:
        return None

    net_flow_5d = sum(
        row.get("main_net_inflow") or 0 for row in fund_rows
    )

    # 统计连续净流入/流出（从最近日期开始）
    inflows = 0
    outflows = 0
    for row in reversed(fund_rows):
        val = row.get("main_net_inflow") or 0
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
        trend = "近 5 日资金流向交替"

    return {
        "net_flow_5d": net_flow_5d,
        "trend": trend,
    }
