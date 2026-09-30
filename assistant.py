"""
Agentic bank assistant, running on a free local model via Ollama.

User question -> the model decides which tool(s) it needs -> we run the matching
db_tools function against the database -> the result goes back to the model -> it
answers in plain language. The model never sees the database or writes SQL; it only
sees the tool results.

Requires the Ollama app running locally with a tool-capable model pulled
(`ollama pull llama3.2`).

Usage:
    python assistant.py                                  # interactive chat
    python assistant.py "Did C003 have any failed transactions?"
"""

import json
import sys

import ollama

import db_tools

MODEL = "qwen2.5:7b"

SYSTEM_PROMPT = """You are a banking assistant that answers questions about customers' transactions.

Always call a tool to get data before answering, and answer only from the tool results;
never guess or invent figures. Use the smallest tool that answers the question: the
summary for totals, averages, largest purchase and failed-transaction counts; the
category breakdown for "what do they spend on" questions; the full transaction list when
you need individual transactions (merchants, dates, which ones failed); the rankings for
questions comparing or listing all customers (top/bottom spenders, sorted lists). Present
rankings in the order the tool returns them.

Definitions: "spending" means completed transactions with a positive amount. Failed,
unknown-status, and refund (negative) transactions are not spending. Amounts are in CAD.

If a tool says a customer doesn't exist, say so. Keep answers short and direct."""


def _tool(name: str, description: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Customer ID, e.g. C003."},
                },
                "required": ["customer_id"],
            },
        },
    }


TOOLS = [
    _tool(
        "get_customer_summary",
        "Get a customer's headline stats: total spending, number of transactions, "
        "average transaction, largest transaction, and number of failed transactions.",
    ),
    _tool(
        "get_customer_transactions",
        "List every transaction for a customer (date, merchant, category, amount, "
        "currency, status), including failed and unknown-status ones.",
    ),
    _tool(
        "get_category_breakdown",
        "Get a customer's spending grouped by category, largest category first, "
        "with the total and number of transactions per category.",
    ),
    {
        "type": "function",
        "function": {
            "name": "get_customer_rankings",
            "description": (
                "List all customers ranked by total spending, already sorted. Use for "
                "questions about every customer, top/bottom spenders, or sorted lists."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order": {
                        "type": "string",
                        "enum": ["asc", "desc"],
                        "description": "'asc' = lowest spending first, 'desc' = highest first.",
                    },
                },
                "required": ["order"],
            },
        },
    },
]

# The only functions the model can trigger.
TOOL_FUNCTIONS = {
    "get_customer_summary": db_tools.get_customer_summary,
    "get_customer_transactions": db_tools.get_customer_transactions,
    "get_category_breakdown": db_tools.get_category_breakdown,
    "get_customer_rankings": db_tools.get_customer_rankings,
}


def run_tool(tool_call) -> dict:
    """Execute one tool call and wrap its output as a tool message."""
    name, args = tool_call.function.name, tool_call.function.arguments
    print(f"  [tool] {name}({json.dumps(args)})")
    try:
        if name not in TOOL_FUNCTIONS:
            result = {"error": f"Unknown tool {name}. Available: {', '.join(TOOL_FUNCTIONS)}"}
        else:
            result = TOOL_FUNCTIONS[name](**args)
    except Exception as e:  # Report failures to the model instead of crashing the loop.
        result = {"error": f"{type(e).__name__}: {e}"}
    return {"role": "tool", "tool_name": name, "content": json.dumps(result)}


class BankAssistant:
    def __init__(self, client: ollama.Client | None = None, model: str = MODEL):
        self.client = client or ollama.Client()
        self.model = model
        # Conversation history, so follow-up questions keep their context.
        self.messages: list = [{"role": "system", "content": SYSTEM_PROMPT}]

    def ask(self, question: str, max_steps: int = 10) -> str:
        self.messages.append({"role": "user", "content": question})

        for _ in range(max_steps):
            response = self.client.chat(
                model=self.model,
                messages=self.messages,
                tools=TOOLS,
                # Deterministic output: small models drift more at higher temperatures.
                options={"temperature": 0},
            )
            message = response.message
            self.messages.append(message)

            if not message.tool_calls:
                return message.content

            for tool_call in message.tool_calls:
                self.messages.append(run_tool(tool_call))

        return "Sorry, I couldn't finish answering that; please try rephrasing the question."


def main() -> None:
    assistant = BankAssistant()

    if len(sys.argv) > 1:
        print(assistant.ask(" ".join(sys.argv[1:])))
        return

    print("Bank assistant. Ask about a customer (e.g. 'What does C003 spend most on?'). Ctrl+C to quit.")
    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if question:
            print(f"Assistant: {assistant.ask(question)}")


if __name__ == "__main__":
    main()
