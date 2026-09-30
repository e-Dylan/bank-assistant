"""
Read-only database tools for the assistant.

The LLM never writes SQL or touches the database directly: it can only call these
functions, which run fixed, parameterized queries against db.db.

Spending rules match customer_stats.py: only completed transactions with a positive
amount count as spending; failed, unknown-status, and refund (negative) rows don't.
"""

import sqlite3
from contextlib import closing
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

DB_PATH = Path(__file__).parent / "db.db"

SPENDING = "status = 'completed' AND amount > 0"


def _connect() -> sqlite3.Connection:
    # mode=ro opens the database read-only, so no tool can modify data.
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_id(customer_id: str) -> str:
    """Accept IDs in any case or with stray spaces (" c003" -> "C003")."""
    return str(customer_id).strip().upper()


def _customer_exists(conn: sqlite3.Connection, customer_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM transactions WHERE customer_id = ? LIMIT 1", (customer_id,)
    ).fetchone()
    return row is not None


def _not_found(customer_id: str) -> dict:
    return {"error": f"Customer {customer_id} not found"}


def get_customer_summary(customer_id: str) -> dict:
    customer_id = _normalize_id(customer_id)
    with closing(_connect()) as conn:
        if not _customer_exists(conn, customer_id):
            return _not_found(customer_id)

        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS number_of_transactions,
                ROUND(COALESCE(SUM(CASE WHEN {SPENDING} THEN amount END), 0.0), 2) AS total_spending,
                COALESCE(MAX(CASE WHEN {SPENDING} THEN amount END), 0.0) AS largest_transaction,
                SUM(status = 'failed') AS failed_transactions
            FROM transactions
            WHERE customer_id = ?
            """,
            (customer_id,),
        ).fetchone()

    summary = {"customer_id": customer_id, **dict(row)}
    # Half-up rounding in Decimal so 606.245 -> 606.25 (float round() would give 606.24).
    average = Decimal(str(summary["total_spending"])) / summary["number_of_transactions"]
    summary["average_transaction"] = float(average.quantize(Decimal("0.01"), ROUND_HALF_UP))
    return summary


def get_customer_transactions(customer_id: str) -> dict:
    customer_id = _normalize_id(customer_id)
    with closing(_connect()) as conn:
        if not _customer_exists(conn, customer_id):
            return _not_found(customer_id)

        rows = conn.execute(
            """
            SELECT transaction_id, date, merchant, category, amount, currency, status
            FROM transactions
            WHERE customer_id = ?
            ORDER BY date, transaction_id
            """,
            (customer_id,),
        ).fetchall()

    return {"customer_id": customer_id, "transactions": [dict(r) for r in rows]}


def get_category_breakdown(customer_id: str) -> dict:
    customer_id = _normalize_id(customer_id)
    with closing(_connect()) as conn:
        if not _customer_exists(conn, customer_id):
            return _not_found(customer_id)

        rows = conn.execute(
            f"""
            SELECT category, ROUND(SUM(amount), 2) AS total, COUNT(*) AS transactions
            FROM transactions
            WHERE customer_id = ? AND {SPENDING}
            GROUP BY category
            ORDER BY total DESC
            """,
            (customer_id,),
        ).fetchall()

    return {"customer_id": customer_id, "spending_by_category": [dict(r) for r in rows]}


def get_customer_rankings(order: str = "desc") -> dict:
    """
    Rank every customer by total spending.

    order: "asc" for lowest spender first, "desc" (default) for highest first.
    Customers with no qualifying spending are included with a total of 0.
    """
    direction = {"asc": "ASC", "desc": "DESC"}.get(str(order).strip().lower())
    if direction is None:
        return {"error": f"Invalid order {order!r}; use 'asc' or 'desc'."}

    with closing(_connect()) as conn:
        # The spending filter lives inside the SUM rather than in WHERE, so customers
        # with no qualifying spending still appear (with 0). `direction` comes from the
        # whitelist above, never from raw input, so formatting it into the SQL is safe.
        rows = conn.execute(
            f"""
            SELECT
                RANK() OVER (ORDER BY total_spending {direction}) AS rank,
                customer_id,
                total_spending
            FROM (
                SELECT
                    customer_id,
                    ROUND(COALESCE(SUM(CASE WHEN {SPENDING} THEN amount END), 0), 2) AS total_spending
                FROM transactions
                GROUP BY customer_id
            )
            ORDER BY total_spending {direction}, customer_id
            """
        ).fetchall()

    return {"order": direction.lower(), "rankings": [dict(r) for r in rows]}