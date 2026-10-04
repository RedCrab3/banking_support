import hashlib
import json
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from agents.classifier import SYSTEM_PROMPT as CLASSIFIER_PROMPT
from agents.feedback import SYSTEM_PROMPT as FEEDBACK_PROMPT
from agents.query import SYSTEM_PROMPT as QUERY_PROMPT
from database.tickets import TicketStore
from evaluation.cases import CASES
from graph.workflow import build_workflow


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def snapshot(store):
    with store.connect() as connection:
        rows = connection.execute(
            "SELECT * FROM support_tickets ORDER BY ticket_number"
        ).fetchall()
        return [dict(row) for row in rows]


def seed_database(store):
    own = store.create_ticket(
        "customer-001", "Evaluation seed complaint.", "seed-own"
    )
    foreign = store.create_ticket(
        "customer-002", "Another customer's complaint.", "seed-foreign"
    )

    with store.connect() as connection:
        connection.execute(
            """
            UPDATE support_tickets
            SET status = 'In Progress'
            WHERE ticket_number = ?
            """,
            (own["ticket_number"],),
        )

    own = store.get_ticket(own["ticket_number"], "customer-001")
    used = {own["ticket_number"], foreign["ticket_number"]}
    missing = next(number for number in range(100000, 100003)
                   if number not in used)

    return own, foreign, missing


def score_case(case, message, result, before, after, own):
    classification_ok = result.get("category") == case["category"]

    expected_handler = (
        "query" if case["category"] == "query" else "feedback"
    )
    route = [step["node"] for step in result.get("trace", [])]
    routing_ok = route == ["classifier", expected_handler]

    outcome_ok = result.get("outcome") == case["outcome"]
    error_free = result.get("error") is None
    ticket = result.get("ticket")

    if case["outcome"] == "complaint_recorded":
        old_numbers = {row["ticket_number"] for row in before}
        new_rows = [
            row for row in after
            if row["ticket_number"] not in old_numbers
        ]
        preserved_rows = [
            row for row in after
            if row["ticket_number"] in old_numbers
        ]

        database_ok = (
            error_free
            and outcome_ok
            and len(new_rows) == 1
            and preserved_rows == before
            and ticket == new_rows[0]
            and ticket["customer_id"] == "customer-001"
            and ticket["complaint"] == message
            and ticket["request_id"] == f"eval-{case['id']}"
            and ticket["status"] == "Open"
        )
    elif case["outcome"] == "ticket_found":
        database_ok = (
            error_free
            and outcome_ok
            and before == after
            and ticket == own
        )
    else:
        database_ok = (
            error_free
            and outcome_ok
            and before == after
            and ticket is None
        )

    response = result.get("response", "")
    response_ok = isinstance(response, str) and bool(response.strip())

    if case["outcome"] == "ticket_found":
        response_ok = response == (
            f"Your ticket #{own['ticket_number']} is currently "
            f"marked as: {own['status']}."
        )
    elif case["outcome"] == "complaint_recorded":
        response_ok = (
            response_ok
            and bool(ticket)
            and f"#{ticket['ticket_number']}" in response
            and f"Current status: {ticket['status']}." in response
        )

    no_fallback = not result.get("used_fallback", False)

    return {
        "classification_ok": classification_ok,
        "routing_ok": routing_ok,
        "database_ok": database_ok,
        "response_facts_ok": response_ok,
        "end_to_end_ok": (
            classification_ok
            and routing_ok
            and database_ok
            and response_ok
            and error_free
            and no_fallback
        ),
    }


def summarize(rows):
    total = len(rows)

    if not total:
        return {}

    metrics = {}

    for key in [
        "classification_ok",
        "routing_ok",
        "database_ok",
        "response_facts_ok",
        "end_to_end_ok",
    ]:
        passed = sum(row["checks"][key] for row in rows)
        metrics[key] = {
            "passed": passed,
            "total": total,
            "percentage": round(100 * passed / total, 2),
        }

    metrics["error_count"] = sum(
        row["result"].get("error") is not None for row in rows
    )
    metrics["fallback_count"] = sum(
        bool(row["result"].get("used_fallback")) for row in rows
    )
    metrics["mean_latency_seconds"] = round(
        sum(row["elapsed_seconds"] for row in rows) / total, 2
    )

    return metrics


def main():
    started_at = datetime.now(timezone.utc)
    run_name = started_at.strftime("%Y%m%dT%H%M%S%fZ")
    report_path = PROJECT_ROOT / "evaluation" / "reports" / (
        f"evaluation_{run_name}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "started_at": started_at.isoformat(),
        "scope": "Single-turn functional workflow evaluation",
        "configured_model": "gpt-4o-mini",
        "planned_cases": len(CASES),
        "dataset_sha256": hashlib.sha256(
            json.dumps(CASES, sort_keys=True).encode()
        ).hexdigest(),
        "prompt_sha256": {
            name: hashlib.sha256(prompt.encode()).hexdigest()
            for name, prompt in {
                "classifier": CLASSIFIER_PROMPT,
                "feedback": FEEDBACK_PROMPT,
                "query": QUERY_PROMPT,
            }.items()
        },
        "versions": {
            name: version(name)
            for name in [
                "langchain", "langchain-openai", "langgraph", "openai"
            ]
        },
        "cases": [],
    }

    for case in CASES:
        with TemporaryDirectory() as folder:
            store = TicketStore(Path(folder) / "evaluation.db")
            own, foreign, missing = seed_database(store)

            message = case["message"].format(
                own_ticket=own["ticket_number"],
                foreign_ticket=foreign["ticket_number"],
                missing_ticket=missing,
            )
            before = snapshot(store)
            started = time.perf_counter()

            try:
                graph = build_workflow(store)
                result = graph.invoke({
                    "customer_id": "customer-001",
                    "customer_name": "Evaluation Customer",
                    "message": message,
                    "request_id": f"eval-{case['id']}",
                })
            except Exception as exc:
                result = {
                    "category": "",
                    "outcome": "error",
                    "response": "",
                    "ticket": None,
                    "trace": [],
                    "error": {
                        "node": "evaluation",
                        "type": type(exc).__name__,
                    },
                    "used_fallback": False,
                }

            elapsed = round(time.perf_counter() - started, 3)
            after = snapshot(store)

            checks = score_case(
                case, message, result, before, after, own
            )

            report["cases"].append({
                "id": case["id"],
                "message": message,
                "expected_category": case["category"],
                "expected_outcome": case["outcome"],
                "elapsed_seconds": elapsed,
                "checks": checks,
                "result": result,
            })

            report["summary"] = summarize(report["cases"])
            report["completed"] = len(report["cases"]) == len(CASES)

            report_path.write_text(
                json.dumps(report, indent=2),
                encoding="utf-8",
            )

            label = "PASS" if checks["end_to_end_ok"] else "FAIL"
            print(
                f"{case['id']} {label} | "
                f"category={result.get('category')} | "
                f"outcome={result.get('outcome')} | "
                f"{elapsed:.2f}s",
                flush=True,
            )

    print("\nSummary:")
    print(json.dumps(report["summary"], indent=2))
    print("\nReport saved:", report_path)


if __name__ == "__main__":
    main()