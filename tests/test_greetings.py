from datetime import datetime, timedelta, timezone

from ui.greetings import should_greet


NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def attempt(attempt_id, completed_at, outcome="feedback_acknowledged"):
    duration = 2.0

    return {
        "attempt_id": attempt_id,
        "created_at": (
            completed_at - timedelta(seconds=duration)
        ).isoformat(),
        "elapsed_seconds": duration,
        "result": {
            "outcome": outcome,
            "response": "Thank you.",
            "error": (
                {"type": "TimeoutError"}
                if outcome == "error"
                else None
            ),
        },
    }


def test_new_conversation_greets():
    assert should_greet([], now=NOW) is True


def test_recent_response_does_not_greet():
    rows = [attempt(1, NOW - timedelta(minutes=4, seconds=59))]
    assert should_greet(rows, now=NOW) is False


def test_five_minute_gap_greets():
    rows = [attempt(1, NOW - timedelta(minutes=5))]
    assert should_greet(rows, now=NOW) is True


def test_latest_completed_response_resets_timer():
    rows = [
        attempt(1, NOW - timedelta(minutes=10)),
        attempt(2, NOW - timedelta(minutes=1)),
    ]
    assert should_greet(rows, now=NOW) is False


def test_failed_attempt_does_not_reset_timer():
    rows = [
        attempt(1, NOW - timedelta(minutes=10)),
        attempt(2, NOW - timedelta(seconds=30), outcome="error"),
    ]
    assert should_greet(rows, now=NOW) is True


def test_only_incomplete_attempts_still_greet():
    rows = [
        attempt(1, NOW - timedelta(seconds=30), outcome="processing"),
    ]
    assert should_greet(rows, now=NOW) is True