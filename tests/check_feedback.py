import os
from pathlib import Path
from tempfile import TemporaryDirectory

from agents.feedback import build_feedback_agent, handle_feedback
from database.tickets import TicketStore


def main():
    agent = build_feedback_agent()

    with TemporaryDirectory() as folder:
        store = TicketStore(Path(folder) / "feedback_check.db")

        cases = [
            (
                "positive_feedback",
                "Thanks for resolving my credit card issue.",
            ),
            (
                "negative_feedback",
                "My replacement debit card still hasn't arrived.",
            ),
        ]

        for index, (category, message) in enumerate(cases):
            result = handle_feedback(
                agent,
                store,
                category=category,
                customer_id="customer-001",
                customer_name="Divya",
                message=message,
                request_id=f"check-{index}",
            )

            print("\nCategory:", category)
            print("Response:", result["response"])
            print("Fallback used:", result["used_fallback"])
            print("Generation error:", result["generation_error"])

            if result["ticket"]:
                print("Ticket:", result["ticket"]["ticket_number"])
                print("Status:", result["ticket"]["status"])

            if result["used_fallback"]:
                raise RuntimeError(
                    "Live generation failed; fallback response was used."
                )

    print("\nBoth live feedback checks completed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        message = str(exc)
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            message = message.replace(api_key, "[REDACTED]")

        print(f"Feedback check failed ({type(exc).__name__}): {message}")
        raise SystemExit(1)