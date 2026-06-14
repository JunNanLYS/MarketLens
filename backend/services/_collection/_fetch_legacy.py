"""Legacy fetch methods (placeholder).

原 7 个 _fetch_kline/_fetch_finance/_fetch_fund_flow/_fetch_technical/
_fetch_dividend/_fetch_reserve/_fetch_shareholder 方法已内联到
_collection/_daily_close.py 的 _fetch_and_build + row_builder 中，
日终 7 类数据采集改用泛型实现。
"""


class _CollectionFetchLegacyMixin:
    """（保留占位，方法已迁移到 _daily_close.py）"""
