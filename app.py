import time
from uuid import uuid4

import streamlit as st

from database.history import HistoryStore
from database.tickets import TicketStore
from graph.persistence import persistent_workflow
from graph.workflow import conversation_config


st.set_page_config(
    page_title="Banking Support Assistant",
    page_icon="🏦",
    layout="wide",
)


DEMO_CUSTOMERS = {
    "customer-001": "Divyabrata",
    "customer-002": "Ananya",
    "customer-003": "Rahul",
}


def save_completed_attempt(history, completed):
    history.update_attempt(
        customer_id=completed["customer_id"],
        conversation_id=completed["conversation_id"],
        attempt_id=completed["attempt_id"],
        result=completed["result"],
        elapsed_seconds=completed["elapsed_seconds"],
    )


def process_request(store, history, conversation_id, request):
    # Save the original request before making model calls.
    try:
        attempt_id = history.record_attempt(
            conversation_id,
            request,
            {
                "response": "This submission has not completed.",
                "outcome": "processing",
                "category": "",
                "trace": [],
                "error": None,
                "ticket": None,
            },
            0.0,
        )
    except Exception as exc:
        st.error(
            f"Could not save the submission: {type(exc).__name__}. "
            "The support workflow was not started."
        )
        st.stop()

    started = time.perf_counter()

    try:
        with persistent_workflow(store) as graph:
            result = graph.invoke(
                request,
                config=conversation_config(
                    request["customer_id"],
                    conversation_id,
                ),
            )
    except Exception as exc:
        result = {
            "category": "",
            "classification_reason": "",
            "response": (
                "I couldn't complete this request. "
                "Please use Retry submission."
            ),
            "outcome": "error",
            "ticket": None,
            "error": {
                "node": "application",
                "type": type(exc).__name__,
            },
            "trace": [],
            "used_fallback": False,
        }

    completed = {
        "customer_id": request["customer_id"],
        "conversation_id": conversation_id,
        "attempt_id": attempt_id,
        "result": result,
        "elapsed_seconds": round(
            time.perf_counter() - started, 2
        ),
    }

    # Retain the result if saving history fails.
    st.session_state.unsaved_attempt = completed

    try:
        save_completed_attempt(history, completed)
    except Exception as exc:
        st.error(
            "The workflow returned a result, but saving its history "
            f"failed: {type(exc).__name__}."
        )
        st.write(result["response"])
        st.info(
            "Use Retry saving history below. "
            "This does not rerun the support workflow."
        )
        st.stop()

    st.session_state.unsaved_attempt = None


def render_details(result, elapsed):
    with st.expander("Execution details"):
        st.write(
            "Classification:",
            result.get("category") or "Unavailable",
        )
        st.write(
            "Reason:",
            result.get("classification_reason", ""),
        )
        st.write("Outcome:", result.get("outcome", ""))
        st.write("Elapsed:", f"{elapsed:.2f} seconds")

        if result.get("used_fallback"):
            st.warning("A fallback acknowledgement was used.")

        if result.get("error"):
            error = result["error"]
            st.error(
                f"Execution failed at {error['node']}: "
                f"{error['type']}"
            )

        st.json(result.get("trace", []))


try:
    store = TicketStore()
    history = HistoryStore()
except Exception as exc:
    st.error(f"Storage setup failed: {type(exc).__name__}")
    st.stop()


# Recover a completed result whose history write failed.
unsaved = st.session_state.get("unsaved_attempt")

if unsaved:
    st.warning("An execution result is waiting to be saved.")
    st.write(unsaved["result"]["response"])

    if st.button("Retry saving history", type="primary"):
        try:
            save_completed_attempt(history, unsaved)
        except Exception as exc:
            st.error(f"History save failed: {type(exc).__name__}")
        else:
            st.session_state.unsaved_attempt = None
            st.rerun()

    st.stop()


with st.sidebar:
    st.title("🏦 Support desk")
    st.caption("Applied Generative AI capstone")

    customer_id = st.selectbox(
        "Demo customer",
        options=list(DEMO_CUSTOMERS),
        format_func=lambda value: (
            f"{DEMO_CUSTOMERS[value]} · {value}"
        ),
        key="demo_customer",
    )
    customer_name = DEMO_CUSTOMERS[customer_id]

    st.info(
        "Demo profiles simulate customer identity. "
        "This selector is not a login system."
    )

    conversation_key = f"conversation_selector_{customer_id}"

    if st.button("New conversation", use_container_width=True):
        new_id = history.create_conversation(customer_id)
        # This widget has not been instantiated in this run yet.
        st.session_state[conversation_key] = new_id

    conversations = history.list_conversations(customer_id)

    if not conversations:
        history.create_conversation(customer_id)
        conversations = history.list_conversations(customer_id)

    conversation_ids = [
        row["conversation_id"] for row in conversations
    ]
    labels = {
        row["conversation_id"]: (
            f"{row['created_at']} · "
            f"{row['conversation_id'][:8]}"
        )
        for row in conversations
    }

    if st.session_state.get(conversation_key) not in conversation_ids:
        st.session_state[conversation_key] = conversation_ids[0]

    conversation_id = st.selectbox(
        "Saved conversation (UTC)",
        options=conversation_ids,
        format_func=lambda value: labels[value],
        key=conversation_key,
    )

    st.caption(
        "Reopen a saved conversation to restore its chat "
        "and remembered ticket."
    )

    st.divider()
    st.markdown("**Try these messages**")
    st.write("Thanks for resolving my login issue.")
    st.write("My replacement debit card hasn't arrived.")
    st.write("Is it resolved yet?")


try:
    tickets = store.list_tickets(customer_id)
    attempts = history.list_attempts(
        customer_id, conversation_id
    )
except Exception as exc:
    st.error(f"Could not load saved data: {type(exc).__name__}")
    st.stop()


# An incomplete or failed latest attempt can be retried.
pending = None

if attempts:
    latest = attempts[-1]
    latest_result = latest["result"]

    if (
        latest_result.get("outcome") in {"processing", "error"}
        or latest_result.get("error")
    ):
        pending = latest["request"]


st.title("Banking Support Assistant")
st.caption(
    "Share feedback, report a problem, or check a support ticket."
)

active_count = sum(
    ticket["status"] != "Closed" for ticket in tickets
)
closed_count = sum(
    ticket["status"] == "Closed" for ticket in tickets
)

col1, col2, col3 = st.columns(3)
col1.metric("Customer", customer_name)
col2.metric("Active tickets", active_count)
col3.metric("Closed tickets", closed_count)

chat_tab, tickets_tab, activity_tab = st.tabs([
    "Chat",
    "My tickets",
    "Execution history",
])


with chat_tab:
    if not attempts:
        st.info(
            f"Welcome, {customer_name}. How can we help you today?"
        )

    shown_requests = set()

    for attempt in attempts:
        request = attempt["request"]
        result = attempt["result"]

        # Display the original customer message once.
        # Keep each retry result visible.
        if request["request_id"] not in shown_requests:
            with st.chat_message("user"):
                st.write(request["message"])
            shown_requests.add(request["request_id"])

        with st.chat_message("assistant"):
            if result.get("outcome") == "processing":
                st.warning(
                    "This submission did not record a final result. "
                    "You can retry it."
                )
            else:
                st.write(result["response"])
                render_details(
                    result,
                    attempt["elapsed_seconds"],
                )

    if pending:
        st.warning(
            "Retry the last submission with its original request ID. "
            "Any ticket already created by that submission will be reused."
        )

        if st.button("Retry submission", type="primary"):
            with st.spinner("Retrying your request…"):
                process_request(
                    store, history, conversation_id, pending
                )
            st.rerun()

    message = st.chat_input(
        "Type your banking support message",
        disabled=pending is not None,
        max_chars=3000,
        submit_mode="disable",
        key=f"chat_{customer_id}_{conversation_id}",
    )

    if message and message.strip():
        request = {
            "customer_id": customer_id,
            "customer_name": customer_name,
            "message": message.strip(),
            "request_id": str(uuid4()),
        }

        with st.spinner("Processing your request…"):
            process_request(
                store, history, conversation_id, request
            )

        st.rerun()


with tickets_tab:
    st.subheader("Your support tickets")

    if tickets:
        st.dataframe(
            tickets,
            hide_index=True,
            use_container_width=True,
            column_config={
                "ticket_number": st.column_config.NumberColumn(
                    "Ticket number",
                    format="%d",
                ),
                "complaint": "Complaint",
                "status": "Status",
                "created_at": "Created at (UTC)",
            },
        )
    else:
        st.info("You haven't raised any tickets yet.")

    if st.button("Refresh saved data"):
        st.rerun()


with activity_tab:
    st.subheader("Saved execution history")

    if not attempts:
        st.info("Execution history will appear after your first message.")
    else:
        rows = [
            {
                "Attempt": item["attempt_id"],
                "Time (UTC)": item["created_at"],
                "Message": item["request"]["message"],
                "Category": item["result"].get("category", ""),
                "Outcome": item["result"].get("outcome", ""),
                "Seconds": item["elapsed_seconds"],
                "Request ID": item["request_id"],
            }
            for item in attempts
        ]

        st.dataframe(
            rows,
            hide_index=True,
            use_container_width=True,
        )

        for attempt in reversed(attempts):
            with st.expander(
                f"Attempt {attempt['attempt_id']}: "
                f"{attempt['result'].get('outcome', '')}"
            ):
                st.write("Request ID:", attempt["request_id"])
                st.json(attempt["result"].get("trace", []))

    st.caption(
        "Conversations, execution history, and ticket context "
        "are stored in SQLite."
    )