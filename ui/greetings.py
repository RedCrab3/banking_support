from datetime import datetime, timedelta, timezone


GREETING_TIMEOUT = timedelta(minutes=5)


def should_greet(attempts, now=None):
    now = now if now is not None else datetime.now(timezone.utc)

    completed = [
        item
        for item in attempts
        if item["result"].get("outcome") not in {
            None, "processing", "error"
        }
        and not item["result"].get("error")
        and bool(item["result"].get("response"))
    ]

    if not completed:
        return True

    latest = max(completed, key=lambda item: item["attempt_id"])

    started_at = datetime.fromisoformat(
        latest["created_at"].replace("Z", "+00:00")
    )

    # Older history records have a submission timestamp and duration.
    completed_at = started_at + timedelta(
        seconds=latest["elapsed_seconds"]
    )

    return now - completed_at >= GREETING_TIMEOUT