from loguru import logger

from backend.storage.database import get_db


class PortfolioService:

    def create_account(self, data: dict) -> dict:
        name: str = data.get("name", "").strip()
        if not name:
            raise ValueError("账户名称不能为空")
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM accounts WHERE name = ? AND deleted_at IS NULL",
                (name,),
            ).fetchone()
            if existing:
                raise ValueError(f"账户名称 '{name}' 已存在")
            broker: str | None = data.get("broker")
            currency: str = data.get("currency", "CNY")
            notes: str | None = data.get("notes")
            cursor = conn.execute(
                "INSERT INTO accounts (name, broker, currency, notes) VALUES (?, ?, ?, ?)",
                (name, broker, currency, notes),
            )
            account_id: int = cursor.lastrowid
            row = conn.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            logger.info("创建账户: id={}, name={}", account_id, name)
            return dict(row)

    def get_accounts(self, include_deleted: bool = False) -> list[dict]:
        with get_db() as conn:
            if include_deleted:
                rows = conn.execute(
                    "SELECT * FROM accounts ORDER BY created_at"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM accounts WHERE deleted_at IS NULL ORDER BY created_at"
                ).fetchall()
            return [dict(row) for row in rows]

    def get_account_by_id(self, account_id: int) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def update_account(self, account_id: int, data: dict) -> dict | None:
        with get_db() as conn:
            existing = conn.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            if existing is None:
                return None
            name: str | None = data.get("name")
            if name is not None:
                name = name.strip()
                if not name:
                    raise ValueError("账户名称不能为空")
                dup = conn.execute(
                    "SELECT id FROM accounts WHERE name = ? AND id != ? AND deleted_at IS NULL",
                    (name, account_id),
                ).fetchone()
                if dup:
                    raise ValueError(f"账户名称 '{name}' 已存在")
            sets: list[str] = []
            params: list = []
            for field in ("name", "broker", "currency", "notes"):
                if field in data:
                    sets.append(f"{field} = ?")
                    params.append(data[field])
            if not sets:
                return dict(existing)
            params.append(account_id)
            conn.execute(
                f"UPDATE accounts SET {', '.join(sets)} WHERE id = ?", params
            )
            row = conn.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            logger.info("更新账户: id={}", account_id)
            return dict(row)

    def delete_account(self, account_id: int) -> bool:
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM accounts WHERE id = ? AND deleted_at IS NULL",
                (account_id,),
            ).fetchone()
            if existing is None:
                return False
            conn.execute(
                "UPDATE accounts SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
                (account_id,),
            )
            logger.info("软删除账户: id={}", account_id)
            return True

    def _get_current_holding(self, account_id: int, symbol: str) -> float:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT type, quantity FROM transactions WHERE account_id = ? AND symbol = ? AND deleted_at IS NULL",
                (account_id, symbol),
            ).fetchall()
        total: float = 0.0
        for row in rows:
            if row["type"] == "buy":
                total += row["quantity"]
            elif row["type"] == "sell":
                total -= row["quantity"]
            elif row["type"] == "split":
                total *= row["quantity"]
        return total

    def create_transaction(self, data: dict) -> dict:
        account_id: int = data["account_id"]
        symbol: str = data["symbol"].strip()
        tx_type: str = data["type"]
        quantity: float = data["quantity"]
        price: float = data["price"]

        with get_db() as conn:
            account = conn.execute(
                "SELECT * FROM accounts WHERE id = ? AND deleted_at IS NULL",
                (account_id,),
            ).fetchone()
            if account is None:
                raise ValueError("账户不存在")

            tracked = conn.execute(
                "SELECT id FROM tracked_assets WHERE symbol = ?", (symbol,)
            ).fetchone()
            if tracked is None:
                logger.warning("标的 {} 不在追踪列表中，建议先添加", symbol)

            if tx_type not in ("buy", "sell", "dividend", "split"):
                raise ValueError(f"无效的交易类型: {tx_type}")

            if quantity <= 0:
                raise ValueError("数量必须大于 0")
            if price <= 0:
                raise ValueError("价格必须大于 0")

            if tx_type == "sell":
                current_holding: float = self._get_current_holding_from_conn(
                    conn, account_id, symbol
                )
                if quantity > current_holding:
                    raise ValueError(
                        f"卖出数量 {quantity} 超过当前持仓 {current_holding}"
                    )

            fee: float = data.get("fee", 0.0)
            currency: str = data.get("currency", account["currency"])
            trade_date: str = data["trade_date"]
            notes: str | None = data.get("notes")

            cursor = conn.execute(
                "INSERT INTO transactions (account_id, symbol, type, quantity, price, fee, currency, trade_date, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (account_id, symbol, tx_type, quantity, price, fee, currency, trade_date, notes),
            )
            tx_id: int = cursor.lastrowid
            row = conn.execute(
                "SELECT * FROM transactions WHERE id = ?", (tx_id,)
            ).fetchone()
            logger.info("创建交易: id={}, type={}, symbol={}", tx_id, tx_type, symbol)
            return dict(row)

    def _get_current_holding_from_conn(
        self, conn, account_id: int, symbol: str
    ) -> float:
        rows = conn.execute(
            "SELECT type, quantity FROM transactions WHERE account_id = ? AND symbol = ? AND deleted_at IS NULL",
            (account_id, symbol),
        ).fetchall()
        total: float = 0.0
        for row in rows:
            if row["type"] == "buy":
                total += row["quantity"]
            elif row["type"] == "sell":
                total -= row["quantity"]
            elif row["type"] == "split":
                total *= row["quantity"]
        return total

    def get_transactions(
        self,
        filters: dict | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        conditions: list[str] = ["t.deleted_at IS NULL"]
        params: list = []

        if filters:
            if "account_id" in filters:
                conditions.append("t.account_id = ?")
                params.append(filters["account_id"])
            if "symbol" in filters:
                conditions.append("t.symbol = ?")
                params.append(filters["symbol"])
            if "type" in filters:
                conditions.append("t.type = ?")
                params.append(filters["type"])
            if "date_from" in filters:
                conditions.append("t.trade_date >= ?")
                params.append(filters["date_from"])
            if "date_to" in filters:
                conditions.append("t.trade_date <= ?")
                params.append(filters["date_to"])

        where_clause: str = " AND ".join(conditions)
        count_sql: str = f"SELECT COUNT(*) FROM transactions t WHERE {where_clause}"
        data_sql: str = (
            f"SELECT t.* FROM transactions t WHERE {where_clause} "
            "ORDER BY t.trade_date DESC, t.created_at DESC "
            "LIMIT ? OFFSET ?"
        )
        offset: int = (page - 1) * page_size

        with get_db() as conn:
            total: int = conn.execute(count_sql, params).fetchone()[0]
            rows = conn.execute(data_sql, params + [page_size, offset]).fetchall()
            items: list[dict] = [dict(row) for row in rows]

        total_pages: int = (total + page_size - 1) // page_size if total > 0 else 0
        return {
            "items": items,
            "page_info": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        }

    def get_transaction_by_id(self, transaction_id: int) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def update_transaction(
        self, transaction_id: int, data: dict
    ) -> dict | None:
        with get_db() as conn:
            existing = conn.execute(
                "SELECT * FROM transactions WHERE id = ? AND deleted_at IS NULL",
                (transaction_id,),
            ).fetchone()
            if existing is None:
                return None

            sets: list[str] = ["updated_at = CURRENT_TIMESTAMP"]
            params: list = []
            for field in ("quantity", "price", "fee", "currency", "trade_date", "notes"):
                if field in data:
                    sets.append(f"{field} = ?")
                    params.append(data[field])
            if len(sets) == 1:
                return dict(existing)

            params.append(transaction_id)
            conn.execute(
                f"UPDATE transactions SET {', '.join(sets)} WHERE id = ?", params
            )

            updated = conn.execute(
                "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
            ).fetchone()
            account_id: int = updated["account_id"]
            symbol: str = updated["symbol"]

            current_holding: float = self._get_current_holding_from_conn(
                conn, account_id, symbol
            )
            if current_holding < 0:
                raise ValueError(
                    f"更新后持仓为负数 ({current_holding})，不允许此操作"
                )

            logger.info("更新交易: id={}", transaction_id)
            return dict(updated)

    def delete_transaction(self, transaction_id: int) -> bool:
        with get_db() as conn:
            existing = conn.execute(
                "SELECT * FROM transactions WHERE id = ? AND deleted_at IS NULL",
                (transaction_id,),
            ).fetchone()
            if existing is None:
                return False

            account_id: int = existing["account_id"]
            symbol: str = existing["symbol"]

            conn.execute(
                "UPDATE transactions SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
                (transaction_id,),
            )

            current_holding: float = self._get_current_holding_from_conn(
                conn, account_id, symbol
            )
            if current_holding < 0:
                conn.execute(
                    "UPDATE transactions SET deleted_at = NULL WHERE id = ?",
                    (transaction_id,),
                )
                raise ValueError(
                    f"删除后持仓将为负数 ({current_holding})，不允许删除"
                )

            logger.info("软删除交易: id={}", transaction_id)
            return True

    def get_positions(
        self, account_id: int | None = None
    ) -> list[dict]:
        with get_db() as conn:
            conditions: list[str] = ["deleted_at IS NULL"]
            params: list = []
            if account_id is not None:
                conditions.append("account_id = ?")
                params.append(account_id)

            where_clause: str = " AND ".join(conditions)
            rows = conn.execute(
                f"SELECT account_id, symbol, type, quantity, price FROM transactions WHERE {where_clause} ORDER BY account_id, symbol, trade_date, created_at",
                params,
            ).fetchall()

        grouped: dict[tuple[int, str], list[dict]] = {}
        for row in rows:
            key: tuple[int, str] = (row["account_id"], row["symbol"])
            grouped.setdefault(key, []).append(dict(row))

        positions: list[dict] = []
        with get_db() as conn:
            for (aid, sym), txs in grouped.items():
                total_qty: float = 0.0
                avg_cost: float = 0.0

                for tx in txs:
                    if tx["type"] == "buy":
                        new_qty: float = total_qty + tx["quantity"]
                        if new_qty > 0:
                            avg_cost = (
                                avg_cost * total_qty + tx["price"] * tx["quantity"]
                            ) / new_qty
                        total_qty = new_qty
                    elif tx["type"] == "sell":
                        total_qty -= tx["quantity"]
                    elif tx["type"] == "dividend":
                        pass
                    elif tx["type"] == "split":
                        total_qty *= tx["quantity"]

                if total_qty <= 1e-9:
                    continue

                quote_row = conn.execute(
                    "SELECT price FROM market_quotes WHERE symbol = ? ORDER BY collected_at DESC LIMIT 1",
                    (sym,),
                ).fetchone()
                current_price: float | None = quote_row["price"] if quote_row else None

                asset_row = conn.execute(
                    "SELECT name FROM tracked_assets WHERE symbol = ?", (sym,)
                ).fetchone()
                asset_name: str | None = asset_row["name"] if asset_row else None

                market_value: float | None = (
                    total_qty * current_price if current_price is not None else None
                )
                unrealized_pnl: float | None = (
                    (current_price - avg_cost) * total_qty
                    if current_price is not None
                    else None
                )
                unrealized_pnl_pct: float | None = (
                    (current_price - avg_cost) / avg_cost * 100
                    if current_price is not None and avg_cost > 0
                    else None
                )

                positions.append(
                    {
                        "account_id": aid,
                        "symbol": sym,
                        "name": asset_name,
                        "total_qty": round(total_qty, 6),
                        "avg_cost": round(avg_cost, 4),
                        "current_price": current_price,
                        "market_value": (
                            round(market_value, 2)
                            if market_value is not None
                            else None
                        ),
                        "unrealized_pnl": (
                            round(unrealized_pnl, 2)
                            if unrealized_pnl is not None
                            else None
                        ),
                        "unrealized_pnl_pct": (
                            round(unrealized_pnl_pct, 2)
                            if unrealized_pnl_pct is not None
                            else None
                        ),
                    }
                )

        return positions

    def get_realized_pnl(
        self,
        account_id: int | None = None,
        symbol: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = ["t.type = 'sell'", "t.deleted_at IS NULL"]
        params: list = []

        if account_id is not None:
            conditions.append("t.account_id = ?")
            params.append(account_id)
        if symbol is not None:
            conditions.append("t.symbol = ?")
            params.append(symbol)

        where_clause: str = " AND ".join(conditions)

        with get_db() as conn:
            sell_rows = conn.execute(
                f"SELECT t.account_id, t.symbol, t.quantity, t.price, t.fee FROM transactions t WHERE {where_clause}",
                params,
            ).fetchall()

            grouped: dict[tuple[int, str], list[dict]] = {}
            for row in sell_rows:
                key: tuple[int, str] = (row["account_id"], row["symbol"])
                grouped.setdefault(key, []).append(
                    {
                        "quantity": row["quantity"],
                        "price": row["price"],
                        "fee": row["fee"],
                    }
                )

            results: list[dict] = []
            for (aid, sym), sells in grouped.items():
                avg_cost: float = self._compute_avg_cost(conn, aid, sym)
                total_realized: float = 0.0
                total_sell_qty: float = 0.0
                for sell in sells:
                    realized: float = (
                        sell["price"] * sell["quantity"]
                        - avg_cost * sell["quantity"]
                        - sell["fee"]
                    )
                    total_realized += realized
                    total_sell_qty += sell["quantity"]

                results.append(
                    {
                        "account_id": aid,
                        "symbol": sym,
                        "total_sell_qty": round(total_sell_qty, 6),
                        "avg_cost": round(avg_cost, 4),
                        "realized_pnl": round(total_realized, 2),
                    }
                )

        return results

    def _compute_avg_cost(
        self, conn, account_id: int, symbol: str
    ) -> float:
        rows = conn.execute(
            "SELECT type, quantity, price FROM transactions WHERE account_id = ? AND symbol = ? AND deleted_at IS NULL ORDER BY trade_date, created_at",
            (account_id, symbol),
        ).fetchall()

        total_qty: float = 0.0
        avg_cost: float = 0.0

        for row in rows:
            if row["type"] == "buy":
                new_qty: float = total_qty + row["quantity"]
                if new_qty > 0:
                    avg_cost = (
                        avg_cost * total_qty + row["price"] * row["quantity"]
                    ) / new_qty
                total_qty = new_qty
            elif row["type"] == "sell":
                total_qty -= row["quantity"]
            elif row["type"] == "dividend":
                pass
            elif row["type"] == "split":
                total_qty *= row["quantity"]

        return avg_cost
