"""临时验证脚本：取 10 条新闻 → DeepSeek 情感分析 → 打印结果。

用法（在项目根目录）：
    uv run python scripts/verify_sentiment.py

环境依赖：
    - DEEPSEEK_API_KEY 已设置（脚本会自检）
    - 网络可达 https://api.deepseek.com 和腾讯新闻接口

脚本不会写入数据库，仅用于人工肉眼校验情感分析链路质量。
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# 允许 `python scripts/verify_sentiment.py` 从仓库根目录直接跑
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from loguru import logger  # noqa: E402

from backend.collectors.tencent_news_http import TencentNewsHTTPProvider  # noqa: E402
from backend.services.sentiment.deepseek_provider import (  # noqa: E402
    DeepSeekSentimentAnalyzer,
)
from backend.services.sentiment.models import SentimentResult  # noqa: E402


TARGET_COUNT = 10


def _fmt_confidence(c: float) -> str:
    """把 0~1 的 confidence 渲染成 ▓▓▓░░░ 进度条 + 数字。"""
    bars = int(round(c * 10))
    return f"{'▓' * bars}{'░' * (10 - bars)} {c:.2f}"


def _fmt_sentiment(s: str) -> str:
    """正负中色字（ANSI），保证 cmd / PowerShell 默认配色都可读。"""
    arrow = {"positive": "↑", "negative": "↓", "neutral": "→"}.get(s, "?")
    return f"{arrow} {s}"


async def fetch_news() -> list[dict]:
    """从腾讯 7×24 拉一批新闻，截前 TARGET_COUNT 条。"""
    provider = TencentNewsHTTPProvider(
        name="tencent_news",
        timeout=30,
        params={"max_items": 50},
        optional=True,
    )
    try:
        items = await provider.fetch_news()
    finally:
        await provider.close()

    logger.info("腾讯新闻原始返回 {} 条", len(items))
    # 去掉标题为空的脏数据，再截 10 条
    items = [it for it in items if (it.get("title") or "").strip()]
    return items[:TARGET_COUNT]


async def analyze(items: list[dict]) -> list[SentimentResult | None]:
    """调用 DeepSeek 对 10 条新闻做情感打分。"""
    analyzer = DeepSeekSentimentAnalyzer(optional=False)  # 强制可用，便于显式失败
    try:
        return await analyzer.analyze(items)
    finally:
        await analyzer.close()


def print_report(items: list[dict], results: list[SentimentResult | None]) -> None:
    """逐条打印 + 汇总分布。"""
    print()
    print("=" * 88)
    print(f"  DeepSeek 情感分析验证 — 共 {len(items)} 条")
    print("=" * 88)

    pos = neg = neu = failed = 0
    confidences: list[float] = []

    for i, (item, result) in enumerate(zip(items, results), start=1):
        title = (item.get("title") or "").strip()
        published = item.get("published_at") or ""
        print(f"\n[{i:02d}] {title[:80]}")
        if published:
            print(f"     发布: {published}")

        if result is None:
            print("     × 分析失败（API 错误 / JSON 解析失败）")
            failed += 1
            continue

        # 写库时实际会用的最终 sentiment（含 0.55 阈值降级）
        db_value = result.to_db_value()
        downgraded = db_value != result.sentiment

        print(f"     原始: {_fmt_sentiment(result.sentiment)}"
              f"   置信: {_fmt_confidence(result.confidence)}")
        print(f"     落库: {_fmt_sentiment(db_value)}"
              f"{'   ⚠ 低置信被降级为 neutral' if downgraded else ''}")
        print(f"     板块: {result.sectors if result.sectors else '—'}")
        print(f"     理由: {result.reason}")

        confidences.append(result.confidence)
        # 用落库后的值统计分布，与生产侧一致
        if db_value == "positive":
            pos += 1
        elif db_value == "negative":
            neg += 1
        else:
            neu += 1

    print("\n" + "=" * 88)
    print("  汇总")
    print("=" * 88)
    print(f"  落库分布:  positive={pos}  negative={neg}  neutral={neu}  failed={failed}")
    if confidences:
        avg = sum(confidences) / len(confidences)
        hi = max(confidences)
        lo = min(confidences)
        downgrade_n = sum(1 for c in confidences if c < 0.55)
        print(f"  置信度:    平均 {avg:.2f}   最高 {hi:.2f}   最低 {lo:.2f}"
              f"   <0.55 被降级 {downgrade_n} 条")
    print("  落库字段:  sentiment 文本 + confidence 原始值 + sentiment_reason 一句话理由 + sectors 涉及板块")
    print("             （news_items.confidence 保留原始置信度，sentiment 列存 to_db_value() 降级后值）")
    print()


async def main() -> int:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("× 未检测到环境变量 DEEPSEEK_API_KEY，无法验证。", file=sys.stderr)
        return 2

    print("→ 正在拉取腾讯 7×24 新闻…")
    items = await fetch_news()
    if not items:
        print("× 拉到的新闻为 0 条，无法继续。"
              "可能是网络问题或腾讯接口变更。", file=sys.stderr)
        return 3
    if len(items) < TARGET_COUNT:
        print(f"⚠ 只拉到 {len(items)} 条（目标 {TARGET_COUNT}），照常进行。")

    print(f"→ 提交 DeepSeek 分析 {len(items)} 条…（temperature=0.1, 并发执行）")
    results = await analyze(items)

    print_report(items, results)
    return 0


if __name__ == "__main__":
    # 屏蔽 loguru 默认 INFO 噪音，让我们的 print 干净一些
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    raise SystemExit(asyncio.run(main()))
