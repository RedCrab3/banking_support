from typing import TypedDict


class SupportInput(TypedDict):
    customer_id: str
    customer_name: str
    message: str
    request_id: str


class SupportState(SupportInput, total=False):
    category: str
    classification_reason: str
    response: str
    ticket: dict | None
    outcome: str
    used_fallback: bool
    generation_error: str | None
    extraction: dict | None
    error: dict | None
    trace: list[dict]
    recent_ticket_number: int | None