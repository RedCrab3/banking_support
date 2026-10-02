import pytest

from database.tickets import TicketStore


@pytest.fixture
def store(tmp_path):
    # Tests use a temporary database, leaving application data untouched.
    return TicketStore(tmp_path / "test.db")


def test_create_and_retrieve_ticket(store):
    ticket = store.create_ticket(
        "customer-001",
        "My replacement debit card has not arrived.",
        "request-001",
    )

    assert 100000 <= ticket["ticket_number"] <= 999999
    assert ticket["status"] == "Open"

    retrieved = store.get_ticket(
        ticket["ticket_number"], "customer-001"
    )
    assert retrieved == ticket


def test_retry_returns_same_ticket(store):
    first = store.create_ticket(
        "customer-001", "Card delivery delayed.", "request-001"
    )
    second = store.create_ticket(
        "customer-001", "Card delivery delayed.", "request-001"
    )

    assert first == second

    with store.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM support_tickets"
        ).fetchone()[0]

    assert count == 1


def test_other_customer_cannot_retrieve_ticket(store):
    ticket = store.create_ticket(
        "customer-001", "Card delivery delayed.", "request-001"
    )

    assert store.get_ticket(
        ticket["ticket_number"], "customer-002"
    ) is None


def test_request_id_cannot_be_reused_for_changed_complaint(store):
    store.create_ticket(
        "customer-001", "Card delivery delayed.", "request-001"
    )

    with pytest.raises(ValueError):
        store.create_ticket(
            "customer-001", "Unexpected bank fee.", "request-001"
        )


def test_missing_ticket_returns_none(store):
    assert store.get_ticket(123456, "customer-001") is None


def test_empty_complaint_is_rejected(store):
    with pytest.raises(ValueError):
        store.create_ticket("customer-001", "   ", "request-001")


def test_ticket_number_collision_is_retried(store, monkeypatch):
    numbers = iter([0, 0, 1])
    monkeypatch.setattr(
        "database.tickets.secrets.randbelow",
        lambda limit: next(numbers),
    )

    first = store.create_ticket(
        "customer-001", "Card delayed.", "request-001"
    )
    second = store.create_ticket(
        "customer-001", "Unexpected fee.", "request-002"
    )

    assert first["ticket_number"] == 100000
    assert second["ticket_number"] == 100001