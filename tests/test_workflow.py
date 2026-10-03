import pytest

from agents.classifier import Classification
from agents.feedback import FeedbackText
from agents.query import TicketQuery
from database.tickets import TicketStore
from graph.workflow import build_workflow


class StubAgent:
    def __init__(self, output):
        self.output = output

    def invoke(self, inputs, config=None):
        return {"structured_response": self.output}


class FailingAgent:
    def invoke(self, inputs, config=None):
        raise TimeoutError("Simulated failure")


def make_graph(store, category, classifier=None):
    if classifier is None:
        classifier = StubAgent(
            Classification(
                category=category,
                reason="Test category.",
            )
        )

    return build_workflow(
        store,
        classifier_agent=classifier,
        feedback_agent=StubAgent(
            FeedbackText(
                acknowledgement="Thank you for your feedback."
            )
        ),
        query_agent=StubAgent(
            TicketQuery(
                is_status_query=True,
                ticket_numbers=[],
            )
        ),
    )


def submission():
    return {
        "customer_id": "customer-001",
        "customer_name": "Divya",
        "message": "My card has not arrived.",
        "request_id": "request-001",
    }


@pytest.mark.parametrize(
    "category,handler,outcome",
    [
        (
            "positive_feedback",
            "feedback",
            "feedback_acknowledged",
        ),
        (
            "negative_feedback",
            "feedback",
            "complaint_recorded",
        ),
        (
            "query",
            "query",
            "missing_ticket_number",
        ),
    ],
)
def test_routes_to_correct_handler(
    tmp_path, category, handler, outcome
):
    store = TicketStore(tmp_path / "test.db")
    graph = make_graph(store, category)

    result = graph.invoke(submission())

    assert [step["node"] for step in result["trace"]] == [
        "classifier",
        handler,
    ]
    assert result["outcome"] == outcome
    assert result["error"] is None
    assert bool(result["ticket"]) == (
        category == "negative_feedback"
    )


def test_classifier_failure_stops_before_ticket_creation(tmp_path):
    store = TicketStore(tmp_path / "test.db")
    graph = make_graph(
        store,
        "negative_feedback",
        classifier=FailingAgent(),
    )

    result = graph.invoke(submission())

    assert result["outcome"] == "error"
    assert result["error"]["node"] == "classifier"
    assert result["error"]["type"] == "TimeoutError"
    assert len(result["trace"]) == 1

    with store.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM support_tickets"
        ).fetchone()[0]

    assert count == 0


def test_retry_through_graph_does_not_duplicate_ticket(tmp_path):
    store = TicketStore(tmp_path / "test.db")
    graph = make_graph(store, "negative_feedback")

    first = graph.invoke(submission())
    second = graph.invoke(submission())

    assert first["outcome"] == "complaint_recorded"
    assert second["outcome"] == "complaint_recorded"
    assert first["ticket"] == second["ticket"]

    with store.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM support_tickets"
        ).fetchone()[0]

    assert count == 1