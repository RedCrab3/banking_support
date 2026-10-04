import pytest

from agents.classifier import Classification
from agents.feedback import FeedbackText
from agents.query import TicketQuery
from database.history import HistoryStore
from database.tickets import TicketStore
from graph.persistence import persistent_workflow
from graph.workflow import conversation_config


class StubAgent:
    def __init__(self, output):
        self.output = output

    def invoke(self, inputs, config=None):
        return {"structured_response": self.output}


def request(message="My card is delayed.", customer_id="customer-001"):
    return {
        "customer_id": customer_id,
        "customer_name": "Test Customer",
        "message": message,
        "request_id": "request-001",
    }


def test_memory_survives_closed_and_reopened_graph(tmp_path):
    ticket_path = tmp_path / "tickets.db"
    checkpoint_path = tmp_path / "checkpoints.db"
    config = conversation_config("customer-001", "conversation-001")

    feedback = StubAgent(
        FeedbackText(acknowledgement="We're sorry for the delay.")
    )
    query = StubAgent(
        TicketQuery(
            is_status_query=True,
            ticket_numbers=[],
            refers_to_recent_ticket=True,
        )
    )

    with persistent_workflow(
        TicketStore(ticket_path),
        checkpoint_path,
        classifier_agent=StubAgent(
            Classification(
                category="negative_feedback",
                reason="Customer reports a delay.",
            )
        ),
        feedback_agent=feedback,
        query_agent=query,
    ) as graph:
        first = graph.invoke(request(), config=config)
        number = first["ticket"]["ticket_number"]

    # Recreate the store, graph, and checkpoint connection.
    with persistent_workflow(
        TicketStore(ticket_path),
        checkpoint_path,
        classifier_agent=StubAgent(
            Classification(
                category="query",
                reason="Customer asks for an update.",
            )
        ),
        feedback_agent=feedback,
        query_agent=query,
    ) as graph:
        follow_up = request("Is it resolved yet?")
        follow_up["request_id"] = "request-002"
        result = graph.invoke(follow_up, config=config)

    assert result["outcome"] == "ticket_found"
    assert result["ticket"]["ticket_number"] == number
    assert result["trace"][-1]["used_memory"] is True


def test_history_survives_reopening_and_is_customer_scoped(tmp_path):
    path = tmp_path / "history.db"
    history = HistoryStore(path)
    conversation_id = history.create_conversation("customer-001")

    saved_result = {
        "response": "Please provide your ticket number.",
        "outcome": "missing_ticket_number",
        "trace": [],
        "error": None,
    }
    history.record_attempt(
        conversation_id,
        request("Check my ticket status."),
        saved_result,
        1.25,
    )

    reopened = HistoryStore(path)
    attempts = reopened.list_attempts(
        "customer-001", conversation_id
    )

    assert len(attempts) == 1
    assert attempts[0]["result"] == saved_result
    assert attempts[0]["elapsed_seconds"] == 1.25
    assert len(reopened.list_conversations("customer-001")) == 1
    assert reopened.list_conversations("customer-002") == []
    assert reopened.list_attempts(
        "customer-002", conversation_id
    ) == []


def test_cannot_record_attempt_for_another_customers_conversation(tmp_path):
    history = HistoryStore(tmp_path / "history.db")
    conversation_id = history.create_conversation("customer-001")

    with pytest.raises(ValueError, match="this customer"):
        history.record_attempt(
            conversation_id,
            request(customer_id="customer-002"),
            {"response": "Test"},
            1.0,
        )


def test_retry_attempts_keep_same_request_id(tmp_path):
    history = HistoryStore(tmp_path / "history.db")
    conversation_id = history.create_conversation("customer-001")
    original_request = request()

    first_id = history.record_attempt(
        conversation_id,
        original_request,
        {"outcome": "error"},
        1.0,
    )
    second_id = history.record_attempt(
        conversation_id,
        original_request,
        {"outcome": "complaint_recorded"},
        1.5,
    )

    attempts = history.list_attempts("customer-001", conversation_id)

    assert first_id != second_id
    assert len(attempts) == 2
    assert attempts[0]["request_id"] == attempts[1]["request_id"]
    
def test_attempt_update_is_saved_and_customer_scoped(tmp_path):
    history = HistoryStore(tmp_path / "history.db")
    conversation_id = history.create_conversation("customer-001")

    attempt_id = history.record_attempt(
        conversation_id,
        request(),
        {"outcome": "processing"},
        0.0,
    )

    with pytest.raises(ValueError):
        history.update_attempt(
            "customer-002",
            conversation_id,
            attempt_id,
            {"outcome": "error"},
            1.0,
        )

    final_result = {
        "outcome": "complaint_recorded",
        "response": "Complaint recorded.",
    }

    history.update_attempt(
        "customer-001",
        conversation_id,
        attempt_id,
        final_result,
        2.5,
    )

    attempts = history.list_attempts(
        "customer-001", conversation_id
    )

    assert len(attempts) == 1
    assert attempts[0]["result"] == final_result
    assert attempts[0]["elapsed_seconds"] == 2.5