from agents.classifier import classify_message
from agents.feedback import handle_feedback
from agents.query import handle_query


def failure(state, node, exc):
    error = {
        "node": node,
        "type": type(exc).__name__,
    }

    return {
        "response": (
            "I couldn't complete this request. Please retry. "
            "If this was a complaint submission, reuse the same "
            "request ID to avoid creating a duplicate ticket."
        ),
        "outcome": "error",
        "error": error,
        "trace": state["trace"] + [
            {
                "node": node,
                "status": "error",
                "error": error["type"],
            }
        ],
    }


def build_nodes(
    store,
    classifier_agent,
    feedback_agent,
    query_agent,
):
    def initialize(state):
        values = {
            name: store.require_text(state.get(name), name)
            for name in [
                "customer_id",
                "customer_name",
                "message",
                "request_id",
            ]
        }

        return {
            **values,
            "category": "",
            "classification_reason": "",
            "response": "",
            "ticket": None,
            "outcome": "",
            "used_fallback": False,
            "generation_error": None,
            "extraction": None,
            "error": None,
            "trace": [],
        }

    def classify(state):
        try:
            result = classify_message(
                classifier_agent,
                state["message"],
            )

            return {
                "category": result.category,
                "classification_reason": result.reason,
                "trace": state["trace"] + [
                    {
                        "node": "classifier",
                        "status": "success",
                        "category": result.category,
                    }
                ],
            }
        except Exception as exc:
            return failure(state, "classifier", exc)

    def route(state):
        if state["error"]:
            return "stop"

        if state["category"] == "query":
            return "query"

        return "feedback"

    def feedback(state):
        try:
            result = handle_feedback(
                feedback_agent,
                store,
                category=state["category"],
                customer_id=state["customer_id"],
                customer_name=state["customer_name"],
                message=state["message"],
                request_id=state["request_id"],
            )

            ticket = result["ticket"]

            outcome = (
                "complaint_recorded"
                if ticket
                else "feedback_acknowledged"
            )

            return {
                **result,
                "outcome": outcome,
                "trace": state["trace"] + [
                    {
                        "node": "feedback",
                        "status": (
                            "fallback"
                            if result["used_fallback"]
                            else "success"
                        ),
                        "outcome": outcome,
                        "ticket_number": (
                            ticket["ticket_number"]
                            if ticket
                            else None
                        ),
                        "generation_error": result["generation_error"],
                    }
                ],
            }
        except Exception as exc:
            return failure(state, "feedback", exc)

    def query(state):
        try:
            result = handle_query(
                query_agent,
                store,
                customer_id=state["customer_id"],
                message=state["message"],
            )

            return {
                **result,
                "trace": state["trace"] + [
                    {
                        "node": "query",
                        "status": "success",
                        "outcome": result["outcome"],
                        "extraction": result["extraction"],
                    }
                ],
            }
        except Exception as exc:
            return failure(state, "query", exc)

    return initialize, classify, route, feedback, query