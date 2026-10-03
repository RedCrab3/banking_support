import time
from datetime import datetime, timezone
from uuid import uuid4

import streamlit as st
from langgraph.checkpoint.memory import InMemorySaver

from database.tickets import TicketStore
from graph.workflow import build_workflow, conversation_config


st.set_page_config(
    page_title="Banking Support Assistant",
    page_icon="🏦",
    layout="wide",
)


DEMO_CUSTOMERS = {
    "customer-001": "Divyabrata Das Gupta",
    "customer-002": "Customer 002",
    "customer-003": "Customer 003",
}


def reset_conversation(customer_id):
    st.session_state.active_customer = customer_id
    st.session_state.conversation_id = str(uuid4())
    st.session_state.messages = []
    st.session_state.runs = []
    st.session_state.pending_request = None


def initialize_session():
    if "support_graph" not in st.session_state:
        store = TicketStore()
        graph = build_workflow(
            store,
            checkpointer=InMemorySaver(),
        )
        st.session_state.ticket_store = store
        st.session_state.support_graph = graph

    if "active_customer" not in st.session_state:
        reset_conversation("customer-001")


def process_request(request):
    started = time.perf_counter()
    config = conversation_config(
        request["customer_id"],
        st.session_state.conversation_id,
    )

    try:
        result = st.session_state.support_graph.invoke(
            request,
            config=config,
        )
    except Exception as exc:
        # Display only the exception type, not raw credential-bearing text.
        result = {
            "category": "",
            "classification_reason": "",
            "response": (
                "I couldn't complete this request. Please use "
                "Retry submission below."
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

    elapsed = round(time.perf_counter() - started, 2)

    st.session_state.messages.append({
        "role": "assistant",
        "content": result["response"],
        "result": result,
        "elapsed": elapsed,
    })

    st.session_state.runs.append({
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "request_id": request["request_id"],
        "message": request["message"],
        "elapsed_seconds": elapsed,
        "result": result,
    })

    if result.get("error"):
        # Preserve the exact submission for an idempotent retry.
        st.session_state.pending_request = request
    else:
        st.session_state.pending_request = None


def render_result_details(result, elapsed):
    with st.expander("Execution details"):
        st.write(
            "Classification:",
            result.get("category") or "Unavailable",
        )
        st.write("Reason:", result.get("classification_reason", ""))
        st.write("Outcome:", result.get("outcome", ""))
        st.write("Elapsed:", f"{elapsed:.2f} seconds")

        if result.get("used_fallback"):
            st.warning("A fallback acknowledgement was used.")

        if result.get("error"):
            st.error(
                "Execution failed at "
                f"{result['error']['node']}: "
                f"{result['error']['type']}"
            )

        st.json(result.get("trace", []))


try:
    initialize_session()
except Exception as exc:
    st.error(f"Application setup failed: {type(exc).__name__}")
    st.info(
        "Check that the lab API environment variables are available "
        "and the database directory is writable."
    )
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
        disabled=st.session_state.pending_request is not None,
    )

    if customer_id != st.session_state.active_customer:
        reset_conversation(customer_id)

    customer_name = DEMO_CUSTOMERS[customer_id]

    st.info(
        "Demo profiles simulate customer identity. "
        "This selector is not a login system."
    )

    if st.button("New conversation", use_container_width=True):
        reset_conversation(customer_id)
        st.rerun()

    st.caption(
        "A new conversation clears chat context. "
        "Saved tickets remain available."
    )

    st.divider()
    st.markdown("**Try these messages**")
    st.write("Thanks for resolving my login issue.")
    st.write("My replacement debit card hasn't arrived.")
    st.write("Is it resolved yet?")
    st.write("What is the status of ticket #123456?")


st.title("Banking Support Assistant")
st.caption(
    "Share feedback, report a problem, or check a support ticket."
)

store = st.session_state.ticket_store

try:
    tickets = store.list_tickets(customer_id)
except Exception as exc:
    st.error(f"Could not load tickets: {type(exc).__name__}")
    st.stop()

active_count = sum(ticket["status"] != "Closed" for ticket in tickets)
closed_count = sum(ticket["status"] == "Closed" for ticket in tickets)

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
    if not st.session_state.messages:
        st.info(
            f"Welcome, {customer_name}. How can we help you today?"
        )

    for entry in st.session_state.messages:
        with st.chat_message(entry["role"]):
            st.write(entry["content"])

            if entry["role"] == "assistant":
                render_result_details(
                    entry["result"],
                    entry["elapsed"],
                )

    pending = st.session_state.pending_request

    if pending:
        st.warning(
            "The last submission failed. Retry it using the same "
            "request ID. If it created a ticket before failing, "
            "the retry will reuse that ticket."
        )

        if st.button("Retry submission", type="primary"):
            with st.spinner("Retrying your request…"):
                process_request(pending)
            st.rerun()

    message = st.chat_input(
        "Type your banking support message",
        disabled=pending is not None,
        max_chars=3000,
        submit_mode="disable",
        key=f"chat_{st.session_state.conversation_id}",
    )

    if message and message.strip():
        request = {
            "customer_id": customer_id,
            "customer_name": customer_name,
            "message": message.strip(),
            "request_id": str(uuid4()),
        }

        st.session_state.pending_request = request
        st.session_state.messages.append({
            "role": "user",
            "content": request["message"],
        })

        with st.spinner("Processing your request…"):
            process_request(request)

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

    if st.button("Refresh tickets"):
        st.rerun()


with activity_tab:
    st.subheader("Current conversation activity")

    runs = st.session_state.runs

    if not runs:
        st.info("Execution history will appear after your first message.")
    else:
        rows = []

        for run in runs:
            result = run["result"]
            rows.append({
                "Time (UTC)": run["time"],
                "Message": run["message"],
                "Category": result.get("category", ""),
                "Outcome": result.get("outcome", ""),
                "Seconds": run["elapsed_seconds"],
                "Request ID": run["request_id"],
            })

        st.dataframe(
            rows,
            hide_index=True,
            use_container_width=True,
        )

        for index, run in reversed(list(enumerate(runs))):
            with st.expander(
                f"Run {index + 1}: {run['result']['outcome']}"
            ):
                st.write("Request ID:", run["request_id"])
                st.json(run["result"].get("trace", []))

    st.caption(
        "Chat and execution history are held in this browser session. "
        "Ticket records are stored in SQLite."
    )