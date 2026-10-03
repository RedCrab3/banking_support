import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from database.tickets import TicketStore
from graph.workflow import build_workflow


def send(graph, message):
    result = graph.invoke({
        "customer_id": "customer-001",
        "customer_name": "Divya",
        "message": message,
        "request_id": str(uuid4()),
    })

    print("\nCustomer:", message)
    print("Category:", result["category"])
    print("Outcome:", result["outcome"])
    print("Response:", result["response"])
    print(
        "Trace:",
        json.dumps(result["trace"], indent=2),
    )

    if result["error"]:
        raise RuntimeError(
            f"Workflow failed: {result['error']}"
        )

    return result


def main():
    with TemporaryDirectory() as folder:
        store = TicketStore(
            Path(folder) / "workflow_check.db"
        )
        graph = build_workflow(store)

        positive = send(
            graph,
            "Thanks for resolving my credit card issue.",
        )
        assert positive["category"] == "positive_feedback"
        assert positive["outcome"] == "feedback_acknowledged"
        assert positive["ticket"] is None
        assert not positive["used_fallback"]

        complaint = send(
            graph,
            "My replacement debit card still hasn't arrived.",
        )
        assert complaint["category"] == "negative_feedback"
        assert complaint["outcome"] == "complaint_recorded"
        assert complaint["ticket"] is not None
        assert not complaint["used_fallback"]

        number = complaint["ticket"]["ticket_number"]

        status = send(
            graph,
            f"What is the status of ticket #{number}?",
        )
        assert status["category"] == "query"
        assert status["outcome"] == "ticket_found"
        assert status["ticket"]["ticket_number"] == number
        assert status["ticket"]["status"] == "Open"

    print("\nAll three end-to-end workflow checks passed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        message = str(exc)
        api_key = os.getenv("OPENAI_API_KEY")

        if api_key:
            message = message.replace(
                api_key, "[REDACTED]"
            )

        print(
            f"Workflow check failed "
            f"({type(exc).__name__}): {message}"
        )
        raise SystemExit(1)