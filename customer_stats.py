import csv
import json
import sys
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

CSV_PATH = Path(__file__).parent / "data" / "transactions.csv"


def load_transactions(path: str = CSV_PATH) -> list[dict]:
    """Load transactions from CSV, parsing amounts as Decimal to avoid float rounding errors."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["amount"] = Decimal(row["amount"])
    return rows


def customer_stats(customer_id: str, transactions: list[dict]) -> dict | None:
    """
    Compute stats for one customer.

    - number_of_transactions counts every transaction, whatever its status.
    - Spending (total, largest, by category) only counts completed transactions
      with a positive amount; failed/unknown-status rows and refunds are excluded.
    - average_transaction is total_spending / number_of_transactions, rounded
      half-up to cents (606.245 -> 606.25).
    - customer_id is matched case-insensitively ("c003" finds C003).
    """
    customer_id = customer_id.strip().upper()
    txns = [t for t in transactions if t["customer_id"] == customer_id]
    if not txns:
        return None

    spending = [t for t in txns if t["status"] == "completed" and t["amount"] > 0]

    total = sum((t["amount"] for t in spending), Decimal("0"))
    by_category = defaultdict(Decimal)
    for t in spending:
        by_category[t["category"]] += t["amount"]

    return {
        "customer_id": customer_id,
        "total_spending": float(total),
        "average_transaction": float((total / len(txns)).quantize(Decimal("0.01"), ROUND_HALF_UP)),
        "number_of_transactions": len(txns),
        "largest_transaction": float(max((t["amount"] for t in spending), default=0)),
        "spending_by_category": {cat: float(amt) for cat, amt in by_category.items()},
        "failed_transactions": sum(1 for t in txns if t["status"] == "failed"),
    }


def all_customer_stats(transactions: list[dict]) -> list[dict]:
    customer_ids = sorted({t["customer_id"] for t in transactions})
    return [customer_stats(cid, transactions) for cid in customer_ids]


if __name__ == "__main__":
    transactions = load_transactions()

    customer = sys.argv[1] if len(sys.argv) > 1 else None

    if customer and len(customer) > 1:
        result = customer_stats(customer, transactions)
        if result is None:
            sys.exit(f"No transactions found for customer {customer}")
    else:
        result = all_customer_stats(transactions)
    print(json.dumps(result, indent=2))
