import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from langgraph.checkpoint.memory import InMemorySaver

from evaluation.challenge_cases import SINGLE_CASES, SCENARIOS
from evaluation.run_evaluation import (
    CLASSIFIER_PROMPT,
    FEEDBACK_PROMPT,
    QUERY_PROMPT,
    PROJECT_ROOT,
    score_case,
    seed_database,
    snapshot,
    summarize,
    version,
)
from database.tickets import TicketStore
from graph.workflow import build_workflow, conversation_config


def main():
    started_at = datetime.now(timezone.utc)
    run_name = started_at.strftime("%Y%m%dT%H%M%S%fZ")

    report_path = (
        PROJECT_ROOT
        / "evaluation"
        / "reports"
        / f"challenge_{run_name}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)

    planned = len(SINGLE_CASES) + 2 * len(SCENARIOS)

    report = {
        "started_at": started_at.isoformat(),
        "scope": "Functional challenge and multi-turn memory evaluation",
        "configured_model": "gpt-4o-mini",
        "planned_submissions": planned,
        "dataset_sha256": hashlib.sha256(
            json.dumps(
                {
                    "single_cases": SINGLE_CASES,
                    "scenarios": SCENARIOS,
                },
                sort_keys=True,
            ).encode()
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
        "completed": False,
    }

    def evaluate_turn(
        graph,
        store,
        case,
        message,
        config,
        expected_ticket,
        expected_memory=False,
    ):
        before = snapshot(store)
        started = time.perf_counter()

        try:
            result = graph.invoke(
                {
                    "customer_id": "customer-001",
                    "customer_name": "Challenge Customer",
                    "message": message,
                    "request_id": f"eval-{case['id']}",
                },
                config=config,
            )
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
            case,
            message,
            result,
            before,
            after,
            expected_ticket,
        )

        query_steps = [
            step
            for step in result.get("trace", [])
            if step["node"] == "query"
        ]
        actual_memory = (
            query_steps[-1].get("used_memory", False)
            if query_steps
            else False
        )

        checks["memory_ok"] = actual_memory == expected_memory
        checks["end_to_end_ok"] = (
            checks["end_to_end_ok"] and checks["memory_ok"]
        )

        report["cases"].append({
            "id": case["id"],
            "message": message,
            "expected_category": case["category"],
            "expected_outcome": case["outcome"],
            "expected_memory": expected_memory,
            "actual_memory": actual_memory,
            "elapsed_seconds": elapsed,
            "checks": checks,
            "result": result,
        })

        report["summary"] = summarize(report["cases"])

        memory_cases = [
            row for row in report["cases"]
            if row["id"].startswith("M") and row["id"].endswith("-2")
        ]
        if memory_cases:
            passed = sum(
                row["checks"]["memory_ok"] for row in memory_cases
            )
            report["summary"]["memory_flag_ok"] = {
                "passed": passed,
                "total": len(memory_cases),
                "percentage": round(
                    100 * passed / len(memory_cases), 2
                ),
            }

        report["completed"] = len(report["cases"]) == planned

        report_path.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

        label = "PASS" if checks["end_to_end_ok"] else "FAIL"
        print(
            f"{case['id']} {label} | "
            f"category={result.get('category')} | "
            f"outcome={result.get('outcome')} | "
            f"memory={actual_memory} | {elapsed:.2f}s",
            flush=True,
        )

        return result

    # Each single-turn case gets a separate database and graph.
    for case in SINGLE_CASES:
        with TemporaryDirectory() as folder:
            store = TicketStore(Path(folder) / "challenge.db")
            own, foreign, missing = seed_database(store)
            graph = build_workflow(store)

            message = case["message"].format(
                own_ticket=own["ticket_number"],
                foreign_ticket=foreign["ticket_number"],
                missing_ticket=missing,
            )

            evaluate_turn(
                graph, store, case, message, None, own
            )

    # Each scenario gets a separate database and memory checkpointer.
    for scenario in SCENARIOS:
        with TemporaryDirectory() as folder:
            store = TicketStore(Path(folder) / "conversation.db")
            own, _, _ = seed_database(store)

            graph = build_workflow(
                store,
                checkpointer=InMemorySaver(),
            )
            config = conversation_config(
                "customer-001", scenario["id"]
            )

            complaint_case = {
                "id": f"{scenario['id']}-1",
                "category": "negative_feedback",
                "outcome": "complaint_recorded",
            }

            first = evaluate_turn(
                graph,
                store,
                complaint_case,
                "My debit card replacement is overdue.",
                config,
                own,
            )

            recent = first.get("ticket")

            # Zero is an invalid placeholder when setup failed.
            # The failed setup remains in the report.
            recent_number = (
                recent["ticket_number"] if recent else 0
            )

            follow_up = scenario["follow_up"].format(
                own_ticket=own["ticket_number"],
                recent_ticket=recent_number,
            )

            follow_case = {
                "id": f"{scenario['id']}-2",
                "category": "query",
                "outcome": scenario["outcome"],
            }

            follow_config = (
                conversation_config(
                    "customer-001", f"{scenario['id']}-new"
                )
                if scenario["new_thread"]
                else config
            )

            target = (
                recent
                if scenario["target"] == "recent"
                else own
            )

            # score_case needs a ticket dictionary for ticket_found.
            # If setup failed, use a deliberately impossible expectation.
            if target is None:
                target = {"ticket_number": 0, "status": "Unavailable"}

            evaluate_turn(
                graph,
                store,
                follow_case,
                follow_up,
                follow_config,
                target,
                expected_memory=scenario["used_memory"],
            )

    print("\nSummary:")
    print(json.dumps(report["summary"], indent=2))
    print("\nReport saved:", report_path)


if __name__ == "__main__":
    main()