import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path


DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "banking_support.db"
)


class TicketStore:
    def __init__(self, db_path=DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row

        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        with self.connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS support_tickets (
                    ticket_number INTEGER PRIMARY KEY
                        CHECK (ticket_number BETWEEN 100000 AND 999999),
                    customer_id TEXT NOT NULL,
                    complaint TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Open'
                        CHECK (
                            status IN (
                                'Open', 'In Progress', 'Closed', 'On Hold'
                            )
                        ),
                    request_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    UNIQUE (customer_id, request_id)
                )
            """)

    @staticmethod
    def require_text(value, name):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string.")
        return value.strip()

    def create_ticket(self, customer_id, complaint, request_id):
        customer_id = self.require_text(customer_id, "customer_id")
        complaint = self.require_text(complaint, "complaint")
        request_id = self.require_text(request_id, "request_id")

        with self.connect() as connection:
            # Serialize writes so two retries cannot create two tickets.
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT * FROM support_tickets
                WHERE customer_id = ? AND request_id = ?
                """,
                (customer_id, request_id),
            ).fetchone()

            if existing:
                if existing["complaint"] != complaint:
                    raise ValueError(
                        "This request_id was already used "
                        "for a different complaint."
                    )
                return dict(existing)

            for _ in range(100):
                ticket_number = 100000 + secrets.randbelow(900000)

                collision = connection.execute(
                    """
                    SELECT 1 FROM support_tickets
                    WHERE ticket_number = ?
                    """,
                    (ticket_number,),
                ).fetchone()

                if collision:
                    continue

                connection.execute(
                    """
                    INSERT INTO support_tickets (
                        ticket_number, customer_id, complaint, request_id
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (ticket_number, customer_id, complaint, request_id),
                )

                row = connection.execute(
                    """
                    SELECT * FROM support_tickets
                    WHERE ticket_number = ? AND customer_id = ?
                    """,
                    (ticket_number, customer_id),
                ).fetchone()

                return dict(row)

            raise RuntimeError(
                "Could not allocate a ticket number. Please retry."
            )

    def get_ticket(self, ticket_number, customer_id):
        customer_id = self.require_text(customer_id, "customer_id")

        if (
            type(ticket_number) is not int
            or not 100000 <= ticket_number <= 999999
        ):
            raise ValueError("ticket_number must be a six-digit integer.")

        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM support_tickets
                WHERE ticket_number = ? AND customer_id = ?
                """,
                (ticket_number, customer_id),
            ).fetchone()

            return dict(row) if row else None


if __name__ == "__main__":
    store = TicketStore()
    print("Database initialized:", store.db_path)