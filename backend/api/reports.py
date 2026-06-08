from datetime import date as _date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, field_validator

from backend.api.neodata import verify_api_key
from backend.services.report_service import ReportService

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

_service = ReportService()

# 与 services/ai_analyzer.py 输出保持一致
Action = Literal["buy", "sell", "watch", "avoid"]
RiskLevel = Literal["low", "medium", "high"]


class GenerateRequest(BaseModel):
    symbols: list[str] | None = None
    force: bool = False

    @field_validator("symbols")
    @classmethod
    def _check_symbols_nonempty(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        cleaned = [s for s in v if s and s.strip()]
        if not cleaned:
            raise ValueError("symbols 必须为非空字符串列表")
        return cleaned


@router.post("/generate", status_code=200)
async def generate_reports(
    body: GenerateRequest,
    _auth: None = Depends(verify_api_key),
) -> dict:
    symbols = body.symbols
    force = body.force
    targets = len(symbols) if symbols else 0
    if targets == 0:
        from backend.services.report_service import ReportService as RS

        active = RS._get_active_symbols()
        targets = len(active)
    result = await _service.generate_reports(symbols=symbols, force=force)
    return {
        "status": "completed",
        "generated": result["generated"],
        "skipped": result["skipped"],
    }


def _validate_iso_date(value: str | None) -> str | None:
    """校验日期字符串符合 ISO 8601 (YYYY-MM-DD)；None 直通。"""
    if value is None:
        return None
    try:
        _date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "INVALID_DATE",
                "detail": f"日期参数必须为 ISO 8601 格式 YYYY-MM-DD，收到: {value!r}",
            },
        )
    return value


@router.get("")
def list_reports(
    action: Action | None = Query(default=None),
    risk_level: RiskLevel | None = Query(default=None),
    date: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    filters: dict = {}
    if action is not None:
        filters["action"] = action
    if risk_level is not None:
        filters["risk_level"] = risk_level
    if date is not None:
        filters["date"] = _validate_iso_date(date)
    return _service.get_reports(filters=filters or None, page=page, page_size=page_size)


@router.get("/{symbol}")
def get_latest_report(symbol: str = Path(..., min_length=1)) -> dict:
    result = _service.get_latest_report(symbol)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "REPORT_NOT_FOUND",
                "detail": f"标的 '{symbol}' 无 AI 报告",
            },
        )
    return result


@router.get("/{symbol}/history")
def get_report_history(
    symbol: str,
    limit: int = Query(default=30, ge=1, le=90),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None, alias="to"),
) -> dict:
    items = _service.get_report_history(
        symbol=symbol,
        limit=limit,
        from_date=_validate_iso_date(from_),
        to_date=_validate_iso_date(to),
    )
    return {"symbol": symbol, "items": items, "total": len(items)}
