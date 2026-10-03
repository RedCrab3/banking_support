import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from database.tickets import TicketStore
from graph.workflow import build_workflow, conversation_config


def send(graph, config, message):
    result = graph.invoke(
        {
            "customer_id": "customer-001",
            "customer_name": "Divya",
            "message": message,
            "request_id": str(uuid4()),
        },
        config=config,
    )

    print("\nCustomer:", message)
    print("Category:", result["category"])
    print("Outcome:", result["outcome"])
    print("Response:", result["response"])
    print("Remembered ticket:", result["recent_ticket_number"])
    print("Trace:", result["trace"])

    if result["error"]:
        raise RuntimeError(f"Workflow error: {result['error']}")

    return result


def main():
    with TemporaryDirectory() as folder:
        store = TicketStore(Path(folder) / "memory_check.db")
        graph = build_workflow(
            store,
            checkpointer=InMemorySaver(),
        )

        config = conversation_config("customer-001", "conversation-1")

        complaint = send(
            graph, config, "My replacement debit card hasn't arrived."
        )
        assert complaint["outcome"] == "complaint_recorded"
        number = complaint["ticket"]["ticket_number"]

        follow_up = send(graph, config, "Is it resolved yet?")
        assert follow_up["outcome"] == "ticket_found"
        assert follow_up["ticket"]["ticket_number"] == number
        assert follow_up["trace"][-1]["used_memory"] is True

        new_config = conversation_config(
            "customer-001", "conversation-2"
        )
        new_chat = send(graph, new_config, "Is it resolved yet?")
        assert new_chat["outcome"] == "missing_ticket_number"

    print("\nAll three live memory checks passed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        message = str(exc)
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            message = message.replace(api_key, "[REDACTED]")

        print(f"Memory check failed ({type(exc).__name__}): {message}")
        raise SystemExit(1)