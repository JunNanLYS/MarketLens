import sqlite3
import json
from datetime import datetime, timezone

from loguru import logger

from backend.services.ai_analyzer import AIAnalyzer
from backend.services.evidence_builder import EvidenceBuilder
from backend.storage.database import get_db


class ReportService:
    """AI 报告生成与查询服务。"""

    @staticmethod
    def generate_reports(
        symbols: list[str] | None = None,
        force: bool = False,
    ) -> dict:
        started_at = datetime.now(timezone.utc).isoformat()
        if not symbols:
            symbols = ReportService._get_active_symbols()
        generated = 0
        skipped = 0
        errors: list[str] = []

        for symbol in symbols:
            try:
                with get_db() as conn:
                    if not force and ReportService._has_today_report(conn, symbol):
                        skipped += 1
                        continue
                    evidence = EvidenceBuilder.build(symbol, conn=conn)
                    result = AIAnalyzer.analyze(evidence)
                    ReportService._save_report(conn, symbol, result, force)
                    generated += 1
            except Exception as e:
                logger.exception("生成报告失败: {}", symbol)
                errors.append(f"{symbol}: {e}")

        finished_at = datetime.now(timezone.utc).isoformat()
        status = "success" if not errors else "failure"
        error_message = "; ".join(errors) if errors else None
        with get_db() as conn:
            conn.execute(
                """INSERT INTO run_logs (task_name, status, started_at, finished_at, error_message, affected_assets)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("ai_report", status, started_at, finished_at, error_message, generated + skipped),
            )

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
    def _has_today_report(conn: sqlite3.Connection, symbol: str) -> bool:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = conn.execute(
            """SELECT id FROM ai_reports
               WHERE symbol = ? AND date(generated_at) = ?
               LIMIT 1""",
            (symbol, today),
        ).fetchone()
        return row is not None

    @staticmethod
    def _save_report(conn: sqlite3.Connection, symbol: str, result: dict, force: bool) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if force:
            conn.execute(
                """DELETE FROM ai_reports
                   WHERE symbol = ? AND date(generated_at) = ?""",
                (symbol, today),
            )
        conn.execute(
            """INSERT INTO ai_reports
               (symbol, action, confidence, risk_level, summary,
                bullish_reasons, bearish_reasons, key_risks, data_used, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                result["generated_at"],
            ),
        )

    @staticmethod
    def _parse_report_row(row: dict) -> dict:
        for key in ["bullish_reasons", "bearish_reasons", "key_risks", "data_used"]:
            val = row.get(key)
            if isinstance(val, str):
                try:
                    row[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    row[key] = []
            elif val is None:
                row[key] = []
        return row
