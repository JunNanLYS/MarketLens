from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/api/v1", tags=["portfolio"])

_service = PortfolioService()


class CreateAccountRequest(BaseModel):
    name: str
    broker: str | None = None
    currency: str = "CNY"
    notes: str | None = None


class UpdateAccountRequest(BaseModel):
    name: str | None = None
    broker: str | None = None
    currency: str | None = None
    notes: str | None = None


class CreateTransactionRequest(BaseModel):
    account_id: int
    symbol: str
    type: str
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = 0.0
    currency: str | None = None
    trade_date: str
    notes: str | None = None


class UpdateTransactionRequest(BaseModel):
    quantity: float | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, gt=0)
    fee: float | None = None
    currency: str | None = None
    trade_date: str | None = None
    notes: str | None = None


@router.post("/accounts", status_code=201)
def create_account(req: CreateAccountRequest) -> dict:
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
def update_account(account_id: int, req: UpdateAccountRequest) -> dict:
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


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int) -> dict:
    success: bool = _service.delete_account(account_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail={"error": "ACCOUNT_NOT_FOUND", "detail": f"账户 {account_id} 不存在"},
        )
    return {"message": "账户已删除"}


@router.post("/transactions", status_code=201)
def create_transaction(req: CreateTransactionRequest) -> dict:
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
    symbol: str | None = None,
    type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
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
        filters["date_from"] = date_from
    if date_to is not None:
        filters["date_to"] = date_to
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
def update_transaction(transaction_id: int, req: UpdateTransactionRequest) -> dict:
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


@router.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: int) -> dict:
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
    return {"message": "交易已删除"}


@router.get("/positions")
def get_positions(account_id: int | None = None) -> list[dict]:
    return _service.get_positions(account_id=account_id)


@router.get("/positions/realized-pnl")
def get_realized_pnl(
    account_id: int | None = None,
    symbol: str | None = None,
) -> list[dict]:
    return _service.get_realized_pnl(account_id=account_id, symbol=symbol)
