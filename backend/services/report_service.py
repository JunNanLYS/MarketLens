import asyncio
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from loguru import logger

from backend.config import get_config
from backend.services.ai_analyzer import AIAnalyzer
from backend.services.collection_service import _WRITE_LOCK
from backend.services.evidence_builder import EvidenceBuilder
from backend.storage.database import get_db, aget_connection


class ReportService:
    """AI 报告生成与查询服务。"""

    @staticmethod
    async def generate_reports(
        symbols: list[str] | None = None,
        force: bool = False,
    ) -> dict:
        """为追踪列表中的标的生成 AI 报告。

        逐标的读取最新数据、构建证据包、调用规则分析器，得到结构化结论
        后写入 ai_reports 表。同一交易日已存在报告时默认跳过；force=True
        时先删除同日期报告再重新生成。

        Args:
            symbols: 标的列表；None 表示读取所有已启用追踪标的。
            force: 是否强制重新生成当日报告（覆盖已有）。

        Returns:
            包含 generated 与 skipped 计数的字典。
        """
        started_at = datetime.now(timezone.utc).isoformat()
        if not symbols:
            symbols = ReportService._get_active_symbols()
        generated = 0
        skipped = 0
        errors: list[str] = []

        # 持有 _WRITE_LOCK 串行化整个报告生成流程：
        # ai_reports 走 aiosqlite 写、run_logs 走 sync get_db 写，两条路径
        # 都属于 CLAUDE.md 硬约束的"writes MUST hold _WRITE_LOCK"。
        # threading.Lock 跨 event loop 安全（scheduler 每次 asyncio.run 新循环）。
        # EvidenceBuilder.build 全程只读，包裹在锁内不阻塞其他读。
        with _WRITE_LOCK:
            # 复用单次 aiosqlite 连接 + PRAGMA，避免每标的重建。
            conn = await aget_connection()
            try:
                for symbol in symbols:
                    try:
                        if not force and await ReportService._has_today_report(
                            conn, symbol
                        ):
                            skipped += 1
                            continue
                        evidence = await EvidenceBuilder.build(symbol, conn=conn)
                        # AIAnalyzer.analyze 是纯 CPU 工作（规则评分 + 字符串拼接），
                        # 在 async 路径中直接调用会阻塞事件循环。用 to_thread 卸载到线程池。
                        result = await asyncio.to_thread(AIAnalyzer.analyze, evidence)
                        await ReportService._save_report(conn, symbol, result, force)
                        generated += 1
                    except Exception as e:
                        logger.exception("生成报告失败: {}", symbol)
                        errors.append(f"{symbol}: {e}")
                await conn.commit()
            finally:
                await conn.close()

            finished_at = datetime.now(timezone.utc).isoformat()
            status = "success" if not errors else "failure"
            error_message = "; ".join(errors) if errors else None
            try:
                with get_db() as conn_sync:
                    conn_sync.execute(
                        """INSERT INTO run_logs (task_name, status, started_at, finished_at, error_message, affected_assets)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            "ai_report",
                            status,
                            started_at,
                            finished_at,
                            error_message,
                            generated + skipped,
                        ),
                    )
            except Exception:
                logger.exception("写入 ai_report run_logs 失败")

        return {"generated": generated, "skipped": skipped}

    @staticmethod
    def get_reports(
        filters: dict | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        conditions: list[str] = []
        params: list = []
        effective_filters = dict(filters) if filters else {}

        if "action" in effective_filters:
            conditions.append("action = ?")
            params.append(effective_filters["action"])
        if "risk_level" in effective_filters:
            conditions.append("risk_level = ?")
            params.append(effective_filters["risk_level"])
        if "date" in effective_filters:
            conditions.append("date(generated_at) = ?")
            params.append(effective_filters["date"])

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        offset = (page - 1) * page_size

        count_sql = f"SELECT COUNT(*) FROM ai_reports {where_clause}"
        data_sql = (
            f"SELECT * FROM ai_reports {where_clause} "
            "ORDER BY generated_at DESC LIMIT ? OFFSET ?"
        )

        with get_db() as conn:
            total = conn.execute(count_sql, params).fetchone()[0]
            rows = conn.execute(data_sql, params + [page_size, offset]).fetchall()

        items = [ReportService._parse_report_row(dict(r)) for r in rows]
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return {
            "items": items,
            "page_info": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        }

    @staticmethod
    def get_latest_report(symbol: str) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                """SELECT ar.* FROM ai_reports ar
                   WHERE ar.symbol = ?
                   ORDER BY ar.generated_at DESC LIMIT 1""",
                (symbol,),
            ).fetchone()
            if row is None:
                return None
            result = ReportService._parse_report_row(dict(row))
            asset_row = conn.execute(
                "SELECT name FROM tracked_assets WHERE symbol = ?",
                (symbol,),
            ).fetchone()
            if asset_row is not None:
                result["name"] = asset_row["name"]
            else:
                result["name"] = None
        return result

    @staticmethod
    def get_report_history(
        symbol: str,
        limit: int = 30,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = ["symbol = ?"]
        params: list = [symbol]
        if from_date is not None:
            conditions.append("date(generated_at) >= ?")
            params.append(from_date)
        if to_date is not None:
            conditions.append("date(generated_at) <= ?")
            params.append(to_date)
        where_clause = "WHERE " + " AND ".join(conditions)
        params.append(min(limit, 90))
        sql = f"SELECT * FROM ai_reports {where_clause} ORDER BY generated_at DESC LIMIT ?"

        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [ReportService._parse_report_row(dict(r)) for r in rows]

    @staticmethod
    def _get_active_symbols() -> list[str]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT symbol FROM tracked_assets WHERE enabled = 1"
            ).fetchall()
        return [r["symbol"] for r in rows]

    @staticmethod
    async def _has_today_report(conn, symbol: str) -> bool:
        tz_name = get_config().get("scheduler", {}).get("timezone", "Asia/Shanghai")
        today = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
        cursor = await conn.execute(
            """SELECT id FROM ai_reports
               WHERE symbol = ? AND date(generated_at) = ?
               LIMIT 1""",
            (symbol, today),
        )
        row = await cursor.fetchone()
        return row is not None

    @staticmethod
    async def _save_report(conn, symbol: str, result: dict, force: bool) -> None:
        tz_name = get_config().get("scheduler", {}).get("timezone", "Asia/Shanghai")
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        today = now.strftime("%Y-%m-%d")
        # 以调度器时区存储 naive datetime，确保 date(generated_at) 与 today 一致
        generated_at = now.replace(tzinfo=None).isoformat()
        if force:
            await conn.execute(
                """DELETE FROM ai_reports
                   WHERE symbol = ? AND date(generated_at) = ?""",
                (symbol, today),
            )
        await conn.execute(
            """INSERT OR IGNORE INTO ai_reports
               (symbol, action, confidence, risk_level, summary,
                bullish_reasons, bearish_reasons, key_risks, data_used,
                sector_exposure, news_ai_scored_pct, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol,
                result["action"],
                result["confidence"],
                result["risk_level"],
                result["summary"],
                json.dumps(result["bullish_reasons"], ensure_ascii=False),
                json.dumps(result["bearish_reasons"], ensure_ascii=False),
                json.dumps(result["key_risks"], ensure_ascii=False),
                json.dumps(result["data_used"], ensure_ascii=False),
                json.dumps(result.get("sector_exposure") or [], ensure_ascii=False),
                result.get("news_ai_scored_pct"),
                generated_at,
            ),
        )

    @staticmethod
    def _parse_report_row(row: dict) -> dict:
        for key in ["bullish_reasons", "bearish_reasons", "key_risks", "data_used", "sector_exposure"]:
            val = row.get(key)
            if isinstance(val, str):
                try:
                    row[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    row[key] = []
            elif val is None:
                row[key] = []
        # news_ai_scored_pct 留作原始 float / None（前端 Progress 渲染）
        return row
