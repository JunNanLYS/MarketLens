from datetime import date as _date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from backend.api.neodata import verify_api_key
from backend.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/api/v1", tags=["portfolio"])

_service = PortfolioService()


# 交易类型白名单（与 services/portfolio_service.py 的 _validate_transaction 保持一致）
TransactionType = Literal["buy", "sell", "dividend", "split"]


def _validate_trade_date(value: str) -> str:
    """校验 trade_date 是 ISO 8601 日期格式 (YYYY-MM-DD)，否则抛 ValueError。"""
    try:
        _date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("trade_date 必须为 ISO 8601 日期格式 YYYY-MM-DD") from exc
    return value


class CreateAccountRequest(BaseModel):
    name: str = Field(..., min_length=1)
    broker: str | None = None
    currency: str = "CNY"
    notes: str | None = None


class UpdateAccountRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    broker: str | None = None
    currency: str | None = None
    notes: str | None = None


class CreateTransactionRequest(BaseModel):
    account_id: int
    symbol: str = Field(..., min_length=1)
    type: TransactionType
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = 0.0
    currency: str | None = None
    trade_date: str
    notes: str | None = None

    @field_validator("trade_date")
    @classmethod
    def _check_trade_date(cls, v: str) -> str:
        return _validate_trade_date(v)


class UpdateTransactionRequest(BaseModel):
    quantity: float | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, gt=0)
    fee: float | None = None
    currency: str | None = None
    trade_date: str | None = None
    notes: str | None = None

    @field_validator("trade_date")
    @classmethod
    def _check_trade_date(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_trade_date(v)


@router.post("/accounts", status_code=201)
def create_account(
    req: CreateAccountRequest,
    _auth: None = Depends(verify_api_key),
) -> dict:
    try:
        return _service.create_account(req.model_dump())
    except ValueError as e:
        if "已存在" in str(e):
            raise HTTPException(
                status_code=409,
                detail={"error": "ACCOUNT_EXISTS", "detail": str(e)},
            )
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_INPUT", "detail": str(e)},
        )


@router.get("/accounts")
def list_accounts(include_deleted: bool = False) -> list[dict]:
    return _service.get_accounts(include_deleted=include_deleted)


@router.get("/accounts/{account_id}")
def get_account(account_id: int) -> dict:
    account: dict | None = _service.get_account_by_id(account_id)
    if account is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "ACCOUNT_NOT_FOUND", "detail": f"账户 {account_id} 不存在"},
        )
    return account


@router.patch("/accounts/{account_id}")
def update_account(
    account_id: int,
    req: UpdateAccountRequest,
    _auth: None = Depends(verify_api_key),
) -> dict:
    data: dict = req.model_dump(exclude_none=True)
    if not data:
        account: dict | None = _service.get_account_by_id(account_id)
        if account is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "ACCOUNT_NOT_FOUND", "detail": f"账户 {account_id} 不存在"},
            )
        return account
    try:
        result: dict | None = _service.update_account(account_id, data)
    except ValueError as e:
        if "已存在" in str(e):
            raise HTTPException(
                status_code=409,
                detail={"error": "ACCOUNT_EXISTS", "detail": str(e)},
            )
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_INPUT", "detail": str(e)},
        )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "ACCOUNT_NOT_FOUND", "detail": f"账户 {account_id} 不存在"},
        )
    return result


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(
    account_id: int,
    _auth: None = Depends(verify_api_key),
) -> None:
    success: bool = _service.delete_account(account_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail={"error": "ACCOUNT_NOT_FOUND", "detail": f"账户 {account_id} 不存在"},
        )
    return None


@router.post("/transactions", status_code=201)
def create_transaction(
    req: CreateTransactionRequest,
    _auth: None = Depends(verify_api_key),
) -> dict:
    try:
        return _service.create_transaction(req.model_dump())
    except ValueError as e:
        msg: str = str(e)
        if "超过当前持仓" in msg or "持仓" in msg:
            raise HTTPException(
                status_code=400,
                detail={"error": "INSUFFICIENT_HOLDING", "detail": msg},
            )
        if "账户不存在" in msg:
            raise HTTPException(
                status_code=404,
                detail={"error": "ACCOUNT_NOT_FOUND", "detail": msg},
            )
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_INPUT", "detail": msg},
        )


@router.get("/transactions")
def list_transactions(
    account_id: int | None = None,
    symbol: str | None = Query(default=None, min_length=1),
    type: TransactionType | None = None,
    date_from: _date | None = Query(default=None, description="ISO 格式 YYYY-MM-DD"),
    date_to: _date | None = Query(default=None, description="ISO 格式 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    filters: dict = {}
    if account_id is not None:
        filters["account_id"] = account_id
    if symbol is not None:
        filters["symbol"] = symbol
    if type is not None:
        filters["type"] = type
    if date_from is not None:
        filters["date_from"] = date_from.isoformat()
    if date_to is not None:
        filters["date_to"] = date_to.isoformat()
    return _service.get_transactions(
        filters=filters if filters else None, page=page, page_size=page_size
    )


@router.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: int) -> dict:
    tx: dict | None = _service.get_transaction_by_id(transaction_id)
    if tx is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "TRANSACTION_NOT_FOUND", "detail": f"交易 {transaction_id} 不存在"},
        )
    return tx


@router.patch("/transactions/{transaction_id}")
def update_transaction(
    transaction_id: int,
    req: UpdateTransactionRequest,
    _auth: None = Depends(verify_api_key),
) -> dict:
    data: dict = req.model_dump(exclude_none=True)
    if not data:
        tx: dict | None = _service.get_transaction_by_id(transaction_id)
        if tx is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "TRANSACTION_NOT_FOUND", "detail": f"交易 {transaction_id} 不存在"},
            )
        return tx
    try:
        result: dict | None = _service.update_transaction(transaction_id, data)
    except ValueError as e:
        msg: str = str(e)
        if "持仓为负" in msg:
            raise HTTPException(
                status_code=400,
                detail={"error": "INSUFFICIENT_HOLDING", "detail": msg},
            )
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_INPUT", "detail": msg},
        )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "TRANSACTION_NOT_FOUND", "detail": f"交易 {transaction_id} 不存在"},
        )
    return result


@router.delete("/transactions/{transaction_id}", status_code=204)
def delete_transaction(
    transaction_id: int,
    _auth: None = Depends(verify_api_key),
) -> None:
    try:
        success: bool = _service.delete_transaction(transaction_id)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "INSUFFICIENT_HOLDING", "detail": str(e)},
        )
    if not success:
        raise HTTPException(
            status_code=404,
            detail={"error": "TRANSACTION_NOT_FOUND", "detail": f"交易 {transaction_id} 不存在"},
        )
    return None


@router.get("/positions")
def get_positions(account_id: int | None = None) -> list[dict]:
    return _service.get_positions(account_id=account_id)


@router.get("/positions/realized-pnl")
def get_realized_pnl(
    account_id: int | None = None,
    symbol: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> list[dict]:
    return _service.get_realized_pnl(
        account_id=account_id, symbol=symbol, page=page, page_size=page_size
    )
