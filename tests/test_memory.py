from langgraph.checkpoint.memory import InMemorySaver

from agents.classifier import Classification
from agents.feedback import FeedbackText
from agents.query import TicketQuery
from database.tickets import TicketStore
from graph.workflow import build_workflow, conversation_config


class StubAgent:
    def __init__(self, output):
        self.output = output

    def invoke(self, inputs, config=None):
        return {"structured_response": self.output}


class ClassifierStub:
    def invoke(self, inputs, config=None):
        message = inputs["messages"][0]["content"]
        category = (
            "negative_feedback"
            if message == "My card has not arrived."
            else "query"
        )
        return {
            "structured_response": Classification(
                category=category,
                reason="Test classification.",
            )
        }


def make_graph(store):
    return build_workflow(
        store,
        classifier_agent=ClassifierStub(),
        feedback_agent=StubAgent(
            FeedbackText(
                acknowledgement="We're sorry for the inconvenience."
            )
        ),
        query_agent=StubAgent(
            TicketQuery(
                is_status_query=True,
                ticket_numbers=[],
                refers_to_recent_ticket=True,
            )
        ),
        checkpointer=InMemorySaver(),
    )


def submission(message, request_id, customer_id="customer-001"):
    return {
        "customer_id": customer_id,
        "customer_name": "Divya",
        "message": message,
        "request_id": request_id,
    }


def test_follow_up_uses_remembered_ticket(tmp_path):
    store = TicketStore(tmp_path / "memory.db")
    graph = make_graph(store)
    config = conversation_config("customer-001", "conversation-1")

    complaint = graph.invoke(
        submission("My card has not arrived.", "request-1"),
        config=config,
    )
    number = complaint["ticket"]["ticket_number"]

    follow_up = graph.invoke(
        submission("Is it resolved yet?", "request-2"),
        config=config,
    )

    assert follow_up["outcome"] == "ticket_found"
    assert follow_up["ticket"]["ticket_number"] == number
    assert follow_up["trace"][-1]["used_memory"] is True


def test_other_threads_do_not_inherit_ticket_memory(tmp_path):
    store = TicketStore(tmp_path / "memory.db")
    graph = make_graph(store)

    graph.invoke(
        submission("My card has not arrived.", "request-1"),
        config=conversation_config("customer-001", "conversation-1"),
    )

    for customer_id, conversation_id in [
        ("customer-001", "conversation-2"),
        ("customer-002", "conversation-1"),
    ]:
        result = graph.invoke(
            submission("Is it resolved yet?", "request-2", customer_id),
            config=conversation_config(customer_id, conversation_id),
        )

        assert result["outcome"] == "missing_ticket_number"
        assert result["ticket"] is None
        assert result["recent_ticket_number"] is None