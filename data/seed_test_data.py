#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通过 API 注入测试数据并模拟用户使用流程。"""
import json
from urllib import request, error

API = "http://127.0.0.1:8000/api/v1"


def call(method, path, body=None):
    url = f"{API}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    req = request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8")
            return {"status": resp.status, "body": json.loads(text) if text else {}}
    except error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        return {"status": e.code, "body": body_text}


def step(label, method, path, body=None):
    res = call(method, path, body)
    print(f"[{label}] {method} {path} -> {res['status']}")
    if isinstance(res["body"], (dict, list)):
        s = json.dumps(res["body"], ensure_ascii=False)
        print(s[:800])
    else:
        print(str(res["body"])[:400])
    print("---")
    return res


step("acc-huatai", "POST", "/accounts", {"name": "华泰", "broker": "华泰证券", "currency": "CNY", "notes": "A股主账户"})

assets = [
    {"symbol": "sh600519", "asset_type": "stock", "name": "贵州茅台"},
    {"symbol": "sz000858", "asset_type": "stock", "name": "五粮液"},
    {"symbol": "hk00700", "asset_type": "stock", "name": "腾讯控股"},
    {"symbol": "hk09988", "asset_type": "stock", "name": "阿里巴巴-W"},
    {"symbol": "usAAPL", "asset_type": "stock", "name": "苹果"},
    {"symbol": "usTSLA", "asset_type": "stock", "name": "特斯拉"},
    {"symbol": "sh510300", "asset_type": "etf", "name": "沪深300ETF"},
    {"symbol": "hf_XAU", "asset_type": "commodity", "name": "伦敦金"},
    {"symbol": "nf_AU0", "asset_type": "future", "name": "沪金连续"},
]
for a in assets:
    step(f"add-{a['symbol']}", "POST", "/assets", a)

trades = [
    {"account_id": 1, "symbol": "hk00700", "type": "buy", "quantity": 100, "price": 380.0, "fee": 50, "trade_date": "2025-12-10"},
    {"account_id": 1, "symbol": "hk00700", "type": "buy", "quantity": 100, "price": 420.0, "fee": 50, "trade_date": "2026-02-14"},
    {"account_id": 1, "symbol": "hk00700", "type": "sell", "quantity": 50, "price": 460.0, "fee": 30, "trade_date": "2026-05-20"},
    {"account_id": 2, "symbol": "sh600519", "type": "buy", "quantity": 10, "price": 1680.0, "fee": 5, "trade_date": "2026-01-15"},
    {"account_id": 2, "symbol": "sz000858", "type": "buy", "quantity": 200, "price": 142.0, "fee": 5, "trade_date": "2026-01-22"},
    {"account_id": 2, "symbol": "sz000858", "type": "sell", "quantity": 100, "price": 158.0, "fee": 5, "trade_date": "2026-04-10"},
    {"account_id": 1, "symbol": "usAAPL", "type": "buy", "quantity": 30, "price": 195.0, "fee": 5, "trade_date": "2026-03-05"},
    {"account_id": 1, "symbol": "usTSLA", "type": "buy", "quantity": 20, "price": 250.0, "fee": 5, "trade_date": "2026-03-12"},
    {"account_id": 1, "symbol": "usTSLA", "type": "sell", "quantity": 20, "price": 215.0, "fee": 5, "trade_date": "2026-05-28"},
    {"account_id": 1, "symbol": "hk00700", "type": "dividend", "quantity": 200, "price": 3.2, "fee": 0, "trade_date": "2026-05-15"},
]
for t in trades:
    step(f"tx-{t['symbol']}-{t['type']}", "POST", "/transactions", t)

print("\n========= 1. 追踪标的页 =========")
step("list-assets", "GET", "/assets?page_size=20")

print("\n========= 2. 标的详情（id=3 腾讯） =========")
step("asset-detail", "GET", "/assets/3")

print("\n========= 3. 持仓 =========")
step("positions", "GET", "/positions")

print("\n========= 4. 已实现盈亏 =========")
step("realized", "GET", "/positions/realized-pnl")

print("\n========= 5. 交易记录 =========")
step("transactions", "GET", "/transactions?page_size=20")

print("\n========= 6. AI 报告列表 =========")
step("reports", "GET", "/reports?page_size=20")

print("\n========= 7. 搜索外部标的 =========")
step("search", "POST", "/assets/search", {"keyword": "腾讯"})

print("\n========= 8. 任务状态 =========")
step("tasks", "GET", "/tasks/status")

print("\n========= 9. 行情 =========")
step("quote", "GET", "/data/quotes/hk00700")
