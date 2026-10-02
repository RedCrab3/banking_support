import os

from agents.classifier import build_classifier, classify_message


CASES = [
    (
        "Thanks for resolving my credit card issue.",
        "positive_feedback",
    ),
    (
        "My replacement debit card still hasn't arrived.",
        "negative_feedback",
    ),
    (
        "Could you check the status of ticket 650932?",
        "query",
    ),
    (
        "Thanks, but my card still hasn't arrived.",
        "negative_feedback",
    ),
    (
        "I'm frustrated. Is ticket 650932 resolved yet?",
        "query",
    ),
]


def main():
    agent = build_classifier()
    passed = 0

    for message, expected in CASES:
        result = classify_message(agent, message)
        correct = result.category == expected
        passed += int(correct)

        print(f"\n{'PASS' if correct else 'FAIL'}: {message}")
        print("Expected:", expected)
        print("Actual:", result.category)
        print("Reason:", result.reason)

    print(f"\nPassed {passed}/{len(CASES)} smoke cases.")

    if passed != len(CASES):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        message = str(exc)
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            message = message.replace(api_key, "[REDACTED]")

        print(f"Classifier check failed ({type(exc).__name__}): {message}")
        raise SystemExit(1)