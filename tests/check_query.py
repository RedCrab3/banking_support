import os
from pathlib import Path
from tempfile import TemporaryDirectory

from agents.query import build_query_agent, handle_query
from database.tickets import TicketStore


def main():
    agent = build_query_agent()

    with TemporaryDirectory() as folder:
        store = TicketStore(Path(folder) / "query_check.db")
        ticket = store.create_ticket(
            "customer-001", "Card delivery delayed.", "check-1"
        )
        number = ticket["ticket_number"]
        other_number = 100000 if number != 100000 else 100001

        cases = [
            (f"Status of ticket #{number}?", "ticket_found"),
            ("Is my complaint resolved?", "missing_ticket_number"),
            (
                f"Check tickets {number} and {other_number}.",
                "multiple_ticket_numbers",
            ),
            ("How do I open a savings account?", "unsupported_query"),
        ]

        passed = 0

        for message, expected in cases:
            result = handle_query(
                agent,
                store,
                customer_id="customer-001",
                message=message,
            )
            correct = result["outcome"] == expected
            passed += int(correct)

            print(f"\n{'PASS' if correct else 'FAIL'}: {message}")
            print("Extraction:", result["extraction"])
            print("Outcome:", result["outcome"])
            print("Response:", result["response"])

        print(f"\nPassed {passed}/{len(cases)} live query checks.")

        if passed != len(cases):
            raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        message = str(exc)
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            message = message.replace(api_key, "[REDACTED]")

        print(f"Query check failed ({type(exc).__name__}): {message}")
        raise SystemExit(1)