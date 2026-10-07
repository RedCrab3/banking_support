import json
from uuid import uuid4

from database.tickets import DEFAULT_DB_PATH, TicketStore


class HistoryStore:
    def __init__(self, db_path=DEFAULT_DB_PATH):
        self.store = TicketStore(db_path)
        self.initialize()

    def initialize(self):
        with self.store.connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    customer_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    PRIMARY KEY (customer_id, conversation_id)
                )
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS execution_history (
                    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    elapsed_seconds REAL NOT NULL
                        CHECK (elapsed_seconds >= 0),
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    )
                )
            """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS history_customer_conversation
                ON execution_history (
                    customer_id, conversation_id, attempt_id
                )
            """)

    def create_conversation(self, customer_id, title="New conversation"):
        customer_id = self.store.require_text(
            customer_id, "customer_id"
        )
        title = self.store.require_text(title, "title")
        conversation_id = str(uuid4())

        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations (
                    customer_id, conversation_id, title
                )
                VALUES (?, ?, ?)
                """,
                (customer_id, conversation_id, title),
            )

        return conversation_id

    def list_conversations(self, customer_id):
        customer_id = self.store.require_text(
            customer_id, "customer_id"
        )

        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT conversation_id, title, created_at
                FROM conversations
                WHERE customer_id = ?
                ORDER BY created_at DESC, conversation_id DESC
                """,
                (customer_id,),
            ).fetchall()

        return [dict(row) for row in rows]

    def record_attempt(
        self,
        conversation_id,
        request,
        result,
        elapsed_seconds,
    ):
        customer_id = self.store.require_text(
            request["customer_id"], "customer_id"
        )
        conversation_id = self.store.require_text(
            conversation_id, "conversation_id"
        )
        request_id = self.store.require_text(
            request["request_id"], "request_id"
        )

        # Store only the intended application input fields.
        clean_request = {
            name: self.store.require_text(request[name], name)
            for name in [
                "customer_id",
                "customer_name",
                "message",
                "request_id",
            ]
        }

        with self.store.connect() as connection:
            exists = connection.execute(
                """
                SELECT 1 FROM conversations
                WHERE customer_id = ? AND conversation_id = ?
                """,
                (customer_id, conversation_id),
            ).fetchone()

            if exists is None:
                raise ValueError(
                    "Conversation does not exist for this customer."
                )
            has_attempt = connection.execute(
                """
                SELECT 1 FROM execution_history
                WHERE customer_id = ? AND conversation_id = ?
                LIMIT 1
                """,
                (customer_id, conversation_id),
            ).fetchone()

            if has_attempt is None:
                message = " ".join(clean_request["message"].split())
                title = (
                    message
                    if len(message) <= 15
                    else message[:10] + "..."
                )

                connection.execute(
                    """
                    UPDATE conversations
                    SET title = ?
                    WHERE customer_id = ? AND conversation_id = ?
                    """,
                    (title, customer_id, conversation_id),
                )

            cursor = connection.execute(
                """
                INSERT INTO execution_history (
                    customer_id,
                    conversation_id,
                    request_id,
                    request_json,
                    result_json,
                    elapsed_seconds
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    customer_id,
                    conversation_id,
                    request_id,
                    json.dumps(clean_request),
                    json.dumps(result),
                    elapsed_seconds,
                ),
            )

            return cursor.lastrowid

    def list_attempts(self, customer_id, conversation_id):
        customer_id = self.store.require_text(
            customer_id, "customer_id"
        )
        conversation_id = self.store.require_text(
            conversation_id, "conversation_id"
        )

        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM execution_history
                WHERE customer_id = ? AND conversation_id = ?
                ORDER BY attempt_id
                """,
                (customer_id, conversation_id),
            ).fetchall()

        attempts = []

        for row in rows:
            item = dict(row)
            item["request"] = json.loads(item.pop("request_json"))
            item["result"] = json.loads(item.pop("result_json"))
            attempts.append(item)

        return attempts
    
    def update_attempt(
        self,
        customer_id,
        conversation_id,
        attempt_id,
        result,
        elapsed_seconds,
    ):
        customer_id = self.store.require_text(
            customer_id, "customer_id"
        )
        conversation_id = self.store.require_text(
            conversation_id, "conversation_id"
        )

        with self.store.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE execution_history
                SET result_json = ?, elapsed_seconds = ?
                WHERE customer_id = ?
                  AND conversation_id = ?
                  AND attempt_id = ?
                """,
                (
                    json.dumps(result),
                    elapsed_seconds,
                    customer_id,
                    conversation_id,
                    attempt_id,
                ),
            )

            if cursor.rowcount != 1:
                raise ValueError(
                    "Execution attempt does not exist for this conversation."
                )