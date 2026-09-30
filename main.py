from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from customer_stats import all_customer_stats, customer_stats, load_transactions

app = FastAPI(title="Bank Assistant API")

transactions = load_transactions()


class CustomerStats(BaseModel):
    customer_id: str
    total_spending: float
    average_transaction: float
    largest_transaction: float
    failed_transactions: int
    spending_by_category: dict[str, float]


@app.get("/customers/{customer_id}", response_model=CustomerStats)
def get_customer(customer_id: str) -> CustomerStats:
    stats = customer_stats(customer_id, transactions)
    if stats is None:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
    return CustomerStats(**stats)


@app.get("/customers", response_model=list[CustomerStats])
def get_all_customers() -> list[CustomerStats]:
    return [CustomerStats(**stats) for stats in all_customer_stats(transactions)]
