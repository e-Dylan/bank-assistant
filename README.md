# Bank Assistant

Customer spending analytics over a transactions dataset, available three ways:

- a **command-line script** that prints per-customer stats,
- a **FastAPI** endpoint that serves them as JSON,
- an **AI assistant** that answers plain-English questions ("What category does C003 spend the most on?") using a free local model through [Ollama](https://ollama.com).

The assistant never queries the database directly. It can only call a fixed set of read-only tools, and it answers from what those tools return:

```
User question → LLM picks a tool → db_tools.py runs a SQL query → result → LLM → answer
```

## Project structure

| Path | Purpose |
|---|---|
| `data/transactions.csv` | Source transactions data |
| `import_csv.py` | Loads the CSV into the `transactions` table in `db.db` |
| `customer_stats.py` | Computes per-customer stats from the CSV (CLI) |
| `main.py` | FastAPI app serving customer stats |
| `db_tools.py` | Read-only database tools the assistant can call |
| `assistant.py` | The AI assistant (Ollama tool-calling loop) |
| `query.sql` | Example SQL query: top 3 customers by spending |
| `tests/` | Tests for the database tools |

## Setup

Requires Python 3.10 or newer.

```bash
pip install -r requirements.txt
```

Build the SQLite database from the CSV:

```bash
python import_csv.py
```

This appends rows, so running it twice duplicates the data. To rebuild from scratch, delete `db.db` first.

## Usage

### Customer stats (CLI)

```bash
python customer_stats.py C003   # one customer
python customer_stats.py        # every customer
```

### API

```bash
uvicorn main:app --reload
```

| Endpoint | Returns |
|---|---|
| `GET /customers/{customer_id}` | Stats for one customer, or `404` if it doesn't exist |
| `GET /customers` | Stats for every customer |

Example: `GET /customers/C003`

```json
{
  "customer_id": "C003",
  "total_spending": 2424.98,
  "average_transaction": 606.25,
  "largest_transaction": 1299.99,
  "failed_transactions": 1,
  "spending_by_category": {"Shopping": 2299.98, "Food": 125.0}
}
```

Interactive API docs are at http://127.0.0.1:8000/docs.

Customer IDs aren't case-sensitive: `/customers/c003` works too. The same goes for the CLI and the assistant.

### AI assistant

1. Install [Ollama](https://ollama.com/download) and make sure it's running.
2. Pull the model (set by `MODEL` in `assistant.py`):

   ```bash
   ollama pull qwen2.5:7b
   ```

3. Ask a question, or start an interactive chat:

   ```bash
   python assistant.py "Did C003 have any failed transactions?"
   python assistant.py
   ```

The chat remembers earlier questions, so follow-ups like "And what about C001?" work. Each tool call is printed as it happens:

```
You: List all customers in order of increasing spending.
  [tool] get_customer_rankings({"order": "asc"})
Assistant: 1. C004 - $0.00
           2. C002 - $148.38
           3. C001 - $588.49
           4. C003 - $2424.98
```

Tools available to the assistant:

| Tool | Answers questions like |
|---|---|
| `get_customer_summary(customer_id)` | Total and average spending, largest purchase, number of failed transactions |
| `get_customer_transactions(customer_id)` | Which transactions failed? Where did they shop, and when? |
| `get_category_breakdown(customer_id)` | What category do they spend the most on? |
| `get_customer_rankings(order)` | Who are the top spenders? List customers by spending. |

Smaller models such as `llama3.2` also work but are less reliable on multi-step questions.

### SQL

`query.sql` runs against `db.db`. From the terminal:

```bash
sqlite3 db.db < query.sql
```

In VS Code with the SQLite extension: run **SQLite: Use Database**, pick `db.db`, then **Run Query** (`Ctrl+Shift+Q`).

## How spending is calculated

The CLI, the API, and the assistant all use the same rules:

- **Spending** counts only `completed` transactions with a positive amount. Failed transactions, transactions with status `unknown`, and refunds (negative amounts) are excluded.
- **Number of transactions** counts every transaction, whatever its status.
- **Average transaction** is total spending divided by the number of transactions (including failed ones).

## Tests

```bash
pytest
```

The tests build a temporary database with known data, so they don't depend on (or modify) `db.db`.
