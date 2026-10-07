from agents.feedback import FeedbackText, handle_feedback
from database.tickets import TicketStore
import pytest


class StubAgent:
    def invoke(self, inputs, config=None):
        return {
            "structured_response": FeedbackText(
                acknowledgement="Thank you for sharing your feedback."
            )
        }


class FailingAgent:
    def invoke(self, inputs, config=None):
        raise TimeoutError("Simulated model timeout")


def run_handler(agent, store, category):
    return handle_feedback(
        agent,
        store,
        category=category,
        customer_id="customer-001",
        customer_name="Divya",
        message="My replacement card has not arrived.",
        request_id="request-001",
    )


def test_positive_feedback_does_not_create_ticket(tmp_path):
    store = TicketStore(tmp_path / "test.db")
    result = run_handler(StubAgent(), store, "positive_feedback")

    assert result["ticket"] is None
    assert "Divya" in result["response"]

    with store.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM support_tickets"
        ).fetchone()[0]

    assert count == 0


def test_complaint_retry_keeps_one_ticket(tmp_path):
    store = TicketStore(tmp_path / "test.db")

    first = run_handler(StubAgent(), store, "negative_feedback")
    second = run_handler(StubAgent(), store, "negative_feedback")

    assert first["ticket"] == second["ticket"]
    assert str(first["ticket"]["ticket_number"]) in first["response"]
    assert first["ticket"]["status"] == "Open"

    with store.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM support_tickets"
        ).fetchone()[0]

    assert count == 1


def test_model_failure_still_confirms_saved_ticket(tmp_path):
    store = TicketStore(tmp_path / "test.db")
    result = run_handler(FailingAgent(), store, "negative_feedback")

    assert result["used_fallback"] is True
    assert result["generation_error"] == "TimeoutError"

    ticket = result["ticket"]
    assert store.get_ticket(
        ticket["ticket_number"], "customer-001"
    ) == ticket
    assert str(ticket["ticket_number"]) in result["response"]
    
@pytest.mark.parametrize("show_greeting", [True, False])
def test_greeting_is_controlled_by_flag(tmp_path, show_greeting):
    store = TicketStore(tmp_path / "greeting.db")

    result = handle_feedback(
        StubAgent(),
        store,
        category="positive_feedback",
        customer_id="customer-001",
        customer_name="Divya",
        message="Thanks for your help.",
        request_id="greeting-001",
        show_greeting=show_greeting,
    )

    assert result["response"].startswith("Hi Divya.") == show_greeting
    assert "Thank you for sharing your feedback." in result["response"]