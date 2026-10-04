import pytest

from database.tickets import TicketStore


@pytest.fixture
def store(tmp_path):
    return TicketStore(tmp_path / "status_test.db")


@pytest.fixture
def ticket(store):
    return store.create_ticket(
        "customer-001", "Card delivery delayed.", "request-001"
    )


def test_status_update_records_history(store, ticket):
    number = ticket["ticket_number"]

    updated = store.update_status(
        number,
        "customer-001",
        "In Progress",
        "demo-support",
        expected_status="Open",
    )

    assert updated["status"] == "In Progress"
    assert store.get_ticket(number, "customer-001") == updated

    history = store.list_status_history(number, "customer-001")

    assert len(history) == 1
    assert history[0]["previous_status"] == "Open"
    assert history[0]["new_status"] == "In Progress"
    assert history[0]["operator"] == "demo-support"
    assert history[0]["changed_at"]


def test_multiple_updates_preserve_order(store, ticket):
    number = ticket["ticket_number"]

    for status in ["In Progress", "On Hold", "Closed"]:
        store.update_status(
            number, "customer-001", status, "demo-support"
        )

    history = store.list_status_history(number, "customer-001")

    assert [
        (row["previous_status"], row["new_status"])
        for row in history
    ] == [
        ("Open", "In Progress"),
        ("In Progress", "On Hold"),
        ("On Hold", "Closed"),
    ]


def test_same_status_does_not_add_history(store, ticket):
    number = ticket["ticket_number"]

    unchanged = store.update_status(
        number, "customer-001", "Open", "demo-support"
    )

    assert unchanged == ticket
    assert store.list_status_history(number, "customer-001") == []


def test_invalid_status_is_rejected(store, ticket):
    number = ticket["ticket_number"]

    with pytest.raises(ValueError, match="Invalid ticket status"):
        store.update_status(
            number, "customer-001", "Refunded", "demo-support"
        )

    assert store.get_ticket(number, "customer-001")["status"] == "Open"
    assert store.list_status_history(number, "customer-001") == []


def test_other_customer_cannot_update_or_view_history(store, ticket):
    number = ticket["ticket_number"]

    store.update_status(
        number, "customer-001", "In Progress", "demo-support"
    )

    with pytest.raises(ValueError, match="not found"):
        store.update_status(
            number, "customer-002", "Closed", "demo-support"
        )

    assert store.get_ticket(
        number, "customer-001"
    )["status"] == "In Progress"
    assert store.list_status_history(number, "customer-002") == []


def test_stale_update_is_rejected(store, ticket):
    number = ticket["ticket_number"]

    store.update_status(
        number, "customer-001", "In Progress", "demo-support"
    )

    with pytest.raises(ValueError, match="changed since"):
        store.update_status(
            number,
            "customer-001",
            "Closed",
            "demo-support",
            expected_status="Open",
        )

    assert store.get_ticket(
        number, "customer-001"
    )["status"] == "In Progress"
    assert len(store.list_status_history(number, "customer-001")) == 1


def test_missing_ticket_cannot_be_updated(store):
    with pytest.raises(ValueError, match="not found"):
        store.update_status(
            123456, "customer-001", "Closed", "demo-support"
        )