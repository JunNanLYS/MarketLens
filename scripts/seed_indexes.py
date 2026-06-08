"""Seed tracked_assets 表：追加 12 个 A 股主要指数 symbol。

12 个指数 kline 已实测全活（westock-data-clawhub@1.0.4），走现有
kline(symbol) 通道采集，零新方法/表/端点。

幂等：使用 INSERT OR IGNORE，重复跑不会报错。
"""

from __future__ import annotations

from backend.storage.database import get_db

# 12 个 A 股主要指数（已实测 kline 全活）。
# market 全部 'cn'（项目用 'cn' 标识 A 股，sh/sz 仅作 symbol 前缀）。
INDEXES: list[tuple[str, str, str]] = [
    ("sh000001", "上证综指", "cn"),
    ("sh000016", "上证50", "cn"),
    ("sh000300", "沪深300", "cn"),
    ("sh000510", "中证A500", "cn"),
    ("sh000688", "科创50", "cn"),
    ("sh000852", "中证1000", "cn"),
    ("sh000905", "中证500", "cn"),
    ("sh000941", "中证新能源", "cn"),
    ("sz399006", "创业板指", "cn"),
    ("sz399300", "沪深300(深)", "cn"),
    ("sz399905", "中证500(深)", "cn"),
    ("sz399997", "中证白酒", "cn"),
]


def main() -> None:
    """执行 12 行 INSERT OR IGNORE。"""
    with get_db() as conn:
        before = conn.execute(
            "SELECT COUNT(*) AS n FROM tracked_assets WHERE asset_type = 'index'"
        ).fetchone()["n"]

        for symbol, name, market in INDEXES:
            conn.execute(
                """
                INSERT OR IGNORE INTO tracked_assets
                    (symbol, name, market, asset_type, enabled)
                VALUES (?, ?, ?, 'index', 1)
                """,
                (symbol, name, market),
            )

        conn.commit()

        after = conn.execute(
            "SELECT COUNT(*) AS n FROM tracked_assets WHERE asset_type = 'index'"
        ).fetchone()["n"]

        added = after - before
        print(
            f"指数跟踪 seed 完成: 新增 {added} 个，跳过 {len(INDEXES) - added} 个已存在"
        )
        print(f"当前 tracked_assets 中 asset_type='index' 共 {after} 个")

        # 列出最终落库的所有指数（供校对）
        rows = conn.execute(
            "SELECT symbol, name, market FROM tracked_assets WHERE asset_type = 'index' ORDER BY symbol"
        ).fetchall()
        for row in rows:
            print(f"  {row['symbol']:12s} {row['name']:20s} {row['market']}")


if __name__ == "__main__":
    main()
