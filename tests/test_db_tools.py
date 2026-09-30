"""
Tests for the database tools the assistant calls.

Each test runs against a fresh temporary database (not db.db), so results don't
change if the real data is re-imported. The fixture data mirrors transactions.csv.

Run with:  python -m pytest -v
"""

import sqlite3

import pytest

import db_tools

COLUMNS = ("transaction_id", "customer_id", "date", "merchant", "category", "amount", "currency", "status")

TRANSACTIONS = [
    (1, "C001", "2026-09-01", "Amazon", "Shopping", 129.99, "CAD", "completed"),
    (2, "C001", "2026-09-03", "Starbucks", "Food", 8.50, "CAD", "completed"),
    (3, "C001", "2026-09-05", "Air Canada", "Travel", 450.00, "CAD", "completed"),
    (4, "C002", "2026-09-01", "Amazon", "Shopping", 89.99, "CAD", "completed"),
    (5, "C002", "2026-09-02", "Netflix", "Entertainment", 22.99, "CAD", "completed"),
    (6, "C002", "2026-09-10", "Uber", "Transport", 35.40, "CAD", "completed"),
    (7, "C003", "2026-09-01", "Apple", "Shopping", 1299.99, "CAD", "completed"),
    (8, "C003", "2026-09-04", "Restaurant X", "Food", 125.00, "CAD", "completed"),
    (9, "C003", "2026-09-08", "Uber", "Transport", 41.25, "CAD", "failed"),
    (10, "C003", "2026-09-09", "Apple", "Shopping", 999.99, "CAD", "completed"),
    (11, "C004", "2026-09-10", "Unknown", "Shopping", -50.00, "CAD", "completed"),
    (12, "C004", "2026-09-11", "Unknown", "Shopping", 200.00, "CAD", "unknown"),
]


def make_db(path, rows):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """CREATE TABLE transactions (
                transaction_id INTEGER, customer_id TEXT, date TEXT, merchant TEXT,
                category TEXT, amount REAL, currency TEXT, status TEXT
            )"""
        )
        conn.executemany(f"INSERT INTO transactions VALUES ({', '.join('?' * len(COLUMNS))})", rows)
    conn.close()


@pytest.fixture(autouse=True)
def test_db(tmp_path, monkeypatch):
    """Point db_tools at a temporary database filled with TRANSACTIONS."""
    path = tmp_path / "test.db"
    make_db(path, TRANSACTIONS)
    monkeypatch.setattr(db_tools, "DB_PATH", path)
    return path


def use_rows(tmp_path, monkeypatch, rows):
    """Swap in a database with custom rows, for edge cases the default data doesn't cover."""
    path = tmp_path / "custom.db"
    make_db(path, rows)
    monkeypatch.setattr(db_tools, "DB_PATH", path)


NOT_FOUND = {"error": "Customer C999 not found"}


# --- get_customer_summary ---------------------------------------------------------


class TestCustomerSummary:
    def test_typical_customer(self):
        assert db_tools.get_customer_summary("C003") == {
            "customer_id": "C003",
            "number_of_transactions": 4,
            "total_spending": 2424.98,
            "largest_transaction": 1299.99,
            "failed_transactions": 1,
            "average_transaction": 606.25,
        }

    def test_failed_transactions_excluded_from_spending_but_counted(self):
        summary = db_tools.get_customer_summary("C003")
        assert summary["total_spending"] == 2424.98  # excludes the failed 41.25 Uber
        assert summary["number_of_transactions"] == 4  # but it still counts as a transaction
        assert summary["failed_transactions"] == 1

    def test_customer_without_failures(self):
        summary = db_tools.get_customer_summary("C001")
        assert summary["failed_transactions"] == 0
        assert summary["total_spending"] == 588.49
        assert summary["largest_transaction"] == 450.00

    def test_refunds_and_unknown_status_are_not_spending(self):
        summary = db_tools.get_customer_summary("C004")
        assert summary["number_of_transactions"] == 2
        assert summary["total_spending"] == 0
        assert summary["largest_transaction"] == 0
        assert summary["average_transaction"] == 0
        assert summary["failed_transactions"] == 0

    def test_average_rounds_half_up_to_cents(self):
        # 2424.98 / 4 = 606.245 exactly; float round() would give 606.24.
        assert db_tools.get_customer_summary("C003")["average_transaction"] == 606.25

    def test_average_repeating_decimal(self):
        # 588.49 / 3 = 196.1633...
        assert db_tools.get_customer_summary("C001")["average_transaction"] == 196.16

    def test_unknown_customer(self):
        assert db_tools.get_customer_summary("C999") == NOT_FOUND


# --- get_customer_transactions ----------------------------------------------------


class TestCustomerTransactions:
    def test_returns_all_transactions_in_date_order(self):
        result = db_tools.get_customer_transactions("C003")
        assert result["customer_id"] == "C003"
        assert [t["transaction_id"] for t in result["transactions"]] == [7, 8, 9, 10]
        dates = [t["date"] for t in result["transactions"]]
        assert dates == sorted(dates)

    def test_includes_failed_and_unknown_status(self):
        c003 = db_tools.get_customer_transactions("C003")["transactions"]
        assert [t["status"] for t in c003].count("failed") == 1
        c004 = db_tools.get_customer_transactions("C004")["transactions"]
        assert {t["status"] for t in c004} == {"completed", "unknown"}

    def test_transaction_fields(self):
        first = db_tools.get_customer_transactions("C003")["transactions"][0]
        assert first == {
            "transaction_id": 7,
            "date": "2026-09-01",
            "merchant": "Apple",
            "category": "Shopping",
            "amount": 1299.99,
            "currency": "CAD",
            "status": "completed",
        }

    def test_only_returns_that_customers_transactions(self):
        ids = {t["transaction_id"] for t in db_tools.get_customer_transactions("C001")["transactions"]}
        assert ids == {1, 2, 3}

    def test_same_day_transactions_ordered_by_id(self, tmp_path, monkeypatch):
        use_rows(tmp_path, monkeypatch, [
            (2, "C001", "2026-09-01", "B", "Food", 5.0, "CAD", "completed"),
            (1, "C001", "2026-09-01", "A", "Food", 5.0, "CAD", "completed"),
        ])
        result = db_tools.get_customer_transactions("C001")["transactions"]
        assert [t["transaction_id"] for t in result] == [1, 2]

    def test_unknown_customer(self):
        assert db_tools.get_customer_transactions("C999") == NOT_FOUND


# --- get_category_breakdown -------------------------------------------------------


class TestCategoryBreakdown:
    def test_groups_and_sorts_largest_first(self):
        assert db_tools.get_category_breakdown("C003") == {
            "customer_id": "C003",
            "spending_by_category": [
                {"category": "Shopping", "total": 2299.98, "transactions": 2},
                {"category": "Food", "total": 125.0, "transactions": 1},
            ],
        }

    def test_top_category_answers_spend_most_question(self):
        # "What category does C001 spend the most on?"
        assert db_tools.get_category_breakdown("C001")["spending_by_category"][0]["category"] == "Travel"

    def test_failed_transactions_excluded(self):
        categories = [c["category"] for c in db_tools.get_category_breakdown("C003")["spending_by_category"]]
        assert "Transport" not in categories  # C003's only Transport charge failed

    def test_category_totals_match_summary_total(self):
        for customer_id in ("C001", "C002", "C003"):
            breakdown = db_tools.get_category_breakdown(customer_id)["spending_by_category"]
            total = db_tools.get_customer_summary(customer_id)["total_spending"]
            assert round(sum(c["total"] for c in breakdown), 2) == total

    def test_customer_with_no_spending_has_empty_breakdown(self):
        assert db_tools.get_category_breakdown("C004") == {"customer_id": "C004", "spending_by_category": []}

    def test_unknown_customer(self):
        assert db_tools.get_category_breakdown("C999") == NOT_FOUND


# --- get_customer_rankings --------------------------------------------------------


class TestCustomerRankings:
    def test_ascending(self):
        assert db_tools.get_customer_rankings("asc") == {
            "order": "asc",
            "rankings": [
                {"rank": 1, "customer_id": "C004", "total_spending": 0.0},
                {"rank": 2, "customer_id": "C002", "total_spending": 148.38},
                {"rank": 3, "customer_id": "C001", "total_spending": 588.49},
                {"rank": 4, "customer_id": "C003", "total_spending": 2424.98},
            ],
        }

    def test_descending(self):
        result = db_tools.get_customer_rankings("desc")
        assert result["order"] == "desc"
        assert [r["customer_id"] for r in result["rankings"]] == ["C003", "C001", "C002", "C004"]
        assert [r["rank"] for r in result["rankings"]] == [1, 2, 3, 4]

    def test_defaults_to_descending(self):
        assert db_tools.get_customer_rankings() == db_tools.get_customer_rankings("desc")

    def test_includes_customers_with_no_spending(self):
        ids = {r["customer_id"] for r in db_tools.get_customer_rankings("asc")["rankings"]}
        assert ids == {"C001", "C002", "C003", "C004"}

    def test_totals_match_customer_summaries(self):
        for row in db_tools.get_customer_rankings()["rankings"]:
            assert row["total_spending"] == db_tools.get_customer_summary(row["customer_id"])["total_spending"]

    @pytest.mark.parametrize("order", ["ASC", " asc ", "Asc"])
    def test_order_is_case_and_whitespace_insensitive(self, order):
        assert db_tools.get_customer_rankings(order)["order"] == "asc"

    @pytest.mark.parametrize("order", ["up", "", "ascending", "desc; DROP TABLE transactions"])
    def test_invalid_order_is_rejected(self, order):
        assert "error" in db_tools.get_customer_rankings(order)

    def test_ties_share_a_rank_and_sort_by_customer_id(self, tmp_path, monkeypatch):
        use_rows(tmp_path, monkeypatch, [
            (1, "C002", "2026-09-01", "A", "Food", 50.0, "CAD", "completed"),
            (2, "C001", "2026-09-01", "A", "Food", 50.0, "CAD", "completed"),
            (3, "C003", "2026-09-01", "A", "Food", 10.0, "CAD", "completed"),
        ])
        rankings = db_tools.get_customer_rankings("desc")["rankings"]
        assert [(r["rank"], r["customer_id"]) for r in rankings] == [(1, "C001"), (1, "C002"), (3, "C003")]

    def test_empty_database(self, tmp_path, monkeypatch):
        use_rows(tmp_path, monkeypatch, [])
        assert db_tools.get_customer_rankings() == {"order": "desc", "rankings": []}


# --- Safety -----------------------------------------------------------------------

CUSTOMER_TOOLS = [
    db_tools.get_customer_summary,
    db_tools.get_customer_transactions,
    db_tools.get_category_breakdown,
]


class TestSafety:
    @pytest.mark.parametrize("tool", CUSTOMER_TOOLS)
    @pytest.mark.parametrize("customer_id", ["' OR '1'='1", "C003'; DROP TABLE transactions; --"])
    def test_sql_injection_is_treated_as_plain_text(self, tool, customer_id, test_db):
        result = tool(customer_id)
        assert list(result) == ["error"] and result["error"].endswith("not found")
        with sqlite3.connect(test_db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == len(TRANSACTIONS)
        conn.close()

    @pytest.mark.parametrize("tool", CUSTOMER_TOOLS)
    def test_customer_ids_are_case_and_whitespace_insensitive(self, tool):
        assert tool(" c003 ") == tool("C003")
        assert tool("c003")["customer_id"] == "C003"

    def test_connection_is_read_only(self):
        conn = db_tools._connect()
        try:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("DELETE FROM transactions")
        finally:
            conn.close()
