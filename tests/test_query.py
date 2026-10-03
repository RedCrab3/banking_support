import pytest

from agents.query import TicketQuery, handle_query
from database.tickets import TicketStore


class StubAgent:
    def __init__(self, numbers, is_status_query=True):
        self.query = TicketQuery(
            is_status_query=is_status_query,
            ticket_numbers=numbers,
        )

    def invoke(self, inputs, config=None):
        return {"structured_response": self.query}


@pytest.fixture
def store(tmp_path):
    return TicketStore(tmp_path / "query_test.db")


def test_returns_database_status(store):
    ticket = store.create_ticket("customer-001", "Card delayed.", "req-1")
    number = ticket["ticket_number"]

    with store.connect() as connection:
        connection.execute(
            "UPDATE support_tickets SET status = ? WHERE ticket_number = ?",
            ("In Progress", number),
        )

    result = handle_query(
        StubAgent([number]),
        store,
        customer_id="customer-001",
        message=f"Status of ticket #{number}?",
    )

    assert result["outcome"] == "ticket_found"
    assert result["ticket"]["status"] == "In Progress"
    assert "In Progress" in result["response"]


def test_other_customer_cannot_access_ticket(store):
    ticket = store.create_ticket("customer-001", "Card delayed.", "req-1")
    number = ticket["ticket_number"]

    result = handle_query(
        StubAgent([number]),
        store,
        customer_id="customer-002",
        message=f"Status of ticket {number}?",
    )

    assert result["outcome"] == "ticket_not_found"
    assert result["ticket"] is None
    assert "Card delayed" not in result["response"]


def test_missing_ticket(store):
    result = handle_query(
        StubAgent([123456]),
        store,
        customer_id="customer-001",
        message="Status of ticket 123456?",
    )
    assert result["outcome"] == "ticket_not_found"


def test_missing_number_requests_clarification(store):
    result = handle_query(
        StubAgent([]),
        store,
        customer_id="customer-001",
        message="Is my complaint resolved?",
    )
    assert result["outcome"] == "missing_ticket_number"


def test_multiple_numbers_requests_clarification(store):
    result = handle_query(
        StubAgent([123456, 654321]),
        store,
        customer_id="customer-001",
        message="Check tickets 123456 and 654321.",
    )
    assert result["outcome"] == "multiple_ticket_numbers"


def test_invented_number_is_rejected(store):
    with pytest.raises(ValueError, match="absent from input"):
        handle_query(
            StubAgent([123456]),
            store,
            customer_id="customer-001",
            message="Is my complaint resolved?",
        )


def test_general_question_is_handled(store):
    result = handle_query(
        StubAgent([], is_status_query=False),
        store,
        customer_id="customer-001",
        message="How do I open a savings account?",
    )
    assert result["outcome"] == "unsupported_query"