from backend.storage.database import get_db


def insert(table: str, data: dict) -> int:
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
    with get_db() as conn:
        cursor = conn.execute(sql, list(data.values()))
        return cursor.lastrowid


def get_by_id(table: str, id: int) -> dict | None:
    with get_db() as conn:
        cursor = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)


def list_paginated(
    table: str,
    page: int = 1,
    page_size: int = 20,
    filters: dict | None = None,
    order_by: str | None = None,
) -> dict:
    where_clause = ""
    params: list = []
    if filters:
        conditions = [f"{k} = ?" for k in filters]
        where_clause = "WHERE " + " AND ".join(conditions)
        params = list(filters.values())
    count_sql = f"SELECT COUNT(*) FROM {table} {where_clause}"
    order_clause = f"ORDER BY {order_by}" if order_by else "ORDER BY id"
    offset = (page - 1) * page_size
    data_sql = f"SELECT * FROM {table} {where_clause} {order_clause} LIMIT ? OFFSET ?"
    with get_db() as conn:
        total = conn.execute(count_sql, params).fetchone()[0]
        rows = conn.execute(data_sql, params + [page_size, offset]).fetchall()
        items = [dict(row) for row in rows]
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


def update(table: str, id: int, data: dict) -> bool:
    set_clause = ", ".join([f"{k} = ?" for k in data])
    sql = f"UPDATE {table} SET {set_clause} WHERE id = ?"
    with get_db() as conn:
        cursor = conn.execute(sql, list(data.values()) + [id])
        return cursor.rowcount > 0


def delete(table: str, id: int, soft: bool = False) -> bool:
    if soft:
        sql = f"UPDATE {table} SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?"
    else:
        sql = f"DELETE FROM {table} WHERE id = ?"
    with get_db() as conn:
        cursor = conn.execute(sql, (id,))
        return cursor.rowcount > 0


def execute_query(sql: str, params: tuple = ()) -> list[dict]:
    with get_db() as conn:
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def execute_modify(sql: str, params: tuple = ()) -> int:
    with get_db() as conn:
        cursor = conn.execute(sql, params)
        return cursor.rowcount
