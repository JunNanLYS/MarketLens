import sqlite3
from loguru import logger

from backend.storage.database import get_db, get_connection_sync


class PortfolioService:
    """????????????? CRUD??????????????????"""

    def create_account(self, data: dict) -> dict:
        """??????

        Args:
            data: ?? name?broker?currency?notes ????

        Returns:
            ??????????

        Raises:
            ValueError: ???????????
        """
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
        """???????

        Args:
            include_deleted: ????????????

        Returns:
            ?????????
        """
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
        """? ID ???????

        Args:
            account_id: ?? ID?

        Returns:
            ????????????? None?
        """
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def update_account(self, account_id: int, data: dict) -> dict | None:
        """???????

        Args:
            account_id: ?? ID?
            data: ?????????name?broker?currency?notes??

        Returns:
            ??????????????????? None?

        Raises:
            ValueError: ??????????
        """
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
        """???????? deleted_at??

        Args:
            account_id: ?? ID?

        Returns:
            ?????????????? False??
        """
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

    def create_transaction(self, data: dict) -> dict:
        """????????

        Args:
            data: ?? account_id?symbol?type?quantity?price ???????

        Returns:
            ??????????

        Raises:
            ValueError: ?????????????
        """
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
            "SELECT type, quantity FROM transactions WHERE account_id = ? AND symbol = ? AND deleted_at IS NULL ORDER BY trade_date, created_at",
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

    @staticmethod
    def _compute_position_detail(transactions: list[dict]) -> tuple[float, float]:
        total_qty: float = 0.0
        avg_cost: float = 0.0
        for tx in transactions:
            if tx["type"] == "buy":
                new_qty: float = total_qty + tx["quantity"]
                if new_qty > 0:
                    avg_cost = (avg_cost * total_qty + tx["price"] * tx["quantity"]) / new_qty
                total_qty = new_qty
            elif tx["type"] == "sell":
                total_qty -= tx["quantity"]
            elif tx["type"] == "dividend":
                pass
            elif tx["type"] == "split":
                # N-16: quantity 在 split 类型中表示拆股比率（如 2:1 拆股则 quantity=2）
                total_qty *= tx["quantity"]
        return total_qty, avg_cost

    def get_transactions(
        self,
        filters: dict | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """?????????

        Args:
            filters: ???????account_id?symbol?type?date_from?date_to??
            page: ???
            page_size: ?????

        Returns:
            ?? items ? page_info ????
        """
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
        """? ID ???????

        Args:
            transaction_id: ?? ID?

        Returns:
            ????????????? None?
        """
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
        """??????????????????

        Args:
            transaction_id: ?? ID?
            data: ?????????

        Returns:
            ??????????????????? None?

        Raises:
            ValueError: ????????
        """
        conn = get_connection_sync()
        try:
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

            conn.commit()
            logger.info("更新交易: id={}", transaction_id)
            return dict(updated)
        except Exception:
            conn.rollback()
            logger.exception("更新交易失败，已回滚: id={}", transaction_id)
            raise
        finally:
            conn.close()

    def delete_transaction(self, transaction_id: int) -> bool:
        """???????????????????

        Args:
            transaction_id: ?? ID?

        Returns:
            ?????????????? False??

        Raises:
            ValueError: ????????
        """
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
        """?????????????

        Args:
            account_id: ??????????

        Returns:
            ?????????????????????????
        """
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


        # ????????????? N+1 ??
        all_symbols = list({str(sym) for (_, sym) in grouped})
        quotes_map: dict[str, float | None] = {}
        names_map: dict[str, str | None] = {}
        if all_symbols:
            ph = ', '.join(['?'] * len(all_symbols))
            with get_db() as conn2:
                qrows = conn2.execute(
                    'SELECT mq.symbol, mq.price FROM market_quotes mq WHERE mq.symbol IN (' + ph + ') AND mq.collected_at = (SELECT MAX(collected_at) FROM market_quotes WHERE symbol = mq.symbol)',
                    all_symbols,
                ).fetchall()
                quotes_map = {r['symbol']: r['price'] for r in qrows}
                arows = conn2.execute(
                    'SELECT symbol, name FROM tracked_assets WHERE symbol IN (' + ph + ')',
                    all_symbols,
                ).fetchall()
                names_map = {r['symbol']: r['name'] for r in arows}

        positions: list[dict] = []
        for (aid, sym), txs in grouped.items():
            total_qty, avg_cost = self._compute_position_detail(txs)
            if total_qty <= 1e-9:
                continue

            current_price = quotes_map.get(sym)
            asset_name = names_map.get(sym)

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

    @staticmethod
    def _calc_realized_pnl(transactions: list[dict]) -> dict:
        """统一计算已实现盈亏与最终持仓状态。

        遍历有序交易列表，应用加权平均成本（WAC）算法，统计卖出盈亏。
        卖出不改变 avg_cost（仍以剩余持仓的平均成本计算），仅在 total_qty 归零时
        返回 avg_cost=0 表示该标的已全部清仓。

        Args:
            transactions: 按 trade_date, created_at 排序的交易记录。

        Returns:
            包含 total_qty, avg_cost, total_realized, total_sell_qty 的字典。
        """
        total_qty: float = 0.0
        avg_cost: float = 0.0
        total_realized: float = 0.0
        total_sell_qty: float = 0.0

        for tx in transactions:
            if tx["type"] == "buy":
                new_qty: float = total_qty + tx["quantity"]
                if new_qty > 0:
                    avg_cost = (
                        avg_cost * total_qty + tx["price"] * tx["quantity"]
                    ) / new_qty
                total_qty = new_qty
            elif tx["type"] == "sell":
                # WAC 算法下，avg_cost 保持不变（基于剩余持仓的成本）
                if total_qty > 0:
                    realized: float = (
                        (tx["price"] - avg_cost) * tx["quantity"]
                        - (tx["fee"] or 0)
                    )
                    total_realized += realized
                total_sell_qty += tx["quantity"]
                total_qty -= tx["quantity"]
            elif tx["type"] == "split":
                total_qty *= tx["quantity"]

        return {
            "total_qty": total_qty,
            "avg_cost": avg_cost if total_qty > 1e-9 else 0.0,
            "total_realized": total_realized,
            "total_sell_qty": total_sell_qty,
        }

    def get_realized_pnl(
        self,
        account_id: int | None = None,
        symbol: str | None = None,
    ) -> list[dict]:
        """??????????

        Args:
            account_id: ??????????
            symbol: ??????????

        Returns:
            ??????????
        """
        """??????????????????"""
        conditions: list[str] = ["t.deleted_at IS NULL"]
        params: list = []

        if account_id is not None:
            conditions.append("t.account_id = ?")
            params.append(account_id)
        if symbol is not None:
            conditions.append("t.symbol = ?")
            params.append(symbol)

        where_clause: str = " AND ".join(conditions)

        with get_db() as conn:
            all_rows = conn.execute(
                f"SELECT t.account_id, t.symbol, t.type, t.quantity, t.price, t.fee "
                f"FROM transactions t WHERE {where_clause} "
                "ORDER BY t.account_id, t.symbol, t.trade_date, t.created_at",
                params,
            ).fetchall()

            grouped: dict[tuple[int, str], list[dict]] = {}
            for row in all_rows:
                key: tuple[int, str] = (row["account_id"], row["symbol"])
                grouped.setdefault(key, []).append(dict(row))

            results: list[dict] = []
            for (aid, sym), txs in grouped.items():
                pnl = self._calc_realized_pnl(txs)
                if pnl["total_sell_qty"] > 1e-9:
                    results.append(
                        {
                            "account_id": aid,
                            "symbol": sym,
                            "total_sell_qty": round(pnl["total_sell_qty"], 6),
                            "avg_cost": round(pnl["avg_cost"], 4),
                            "realized_pnl": round(pnl["total_realized"], 2),
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
        rows_as_dicts: list[dict] = [dict(row) for row in rows]
        _, avg_cost = self._compute_position_detail(rows_as_dicts)
        return avg_cost
