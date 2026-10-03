from langgraph.graph import END, START, StateGraph

from agents.classifier import build_classifier
from agents.feedback import build_feedback_agent
from agents.query import build_query_agent
from database.tickets import TicketStore
from graph.nodes import build_nodes
from graph.state import SupportInput, SupportState
import json

def conversation_config(customer_id: str, conversation_id: str):
    customer_id = TicketStore.require_text(customer_id, "customer_id")
    conversation_id = TicketStore.require_text(
        conversation_id, "conversation_id"
    )

    # Scope each conversation to its customer.
    thread_id = json.dumps([customer_id, conversation_id])

    return {"configurable": {"thread_id": thread_id}}

def build_workflow(
    store: TicketStore,
    *,
    classifier_agent=None,
    feedback_agent=None,
    query_agent=None,
    checkpointer=None,
):
    # Inject stub agents in tests to avoid live API calls.
    if classifier_agent is None:
        classifier_agent = build_classifier()

    if feedback_agent is None:
        feedback_agent = build_feedback_agent()

    if query_agent is None:
        query_agent = build_query_agent()

    initialize, classify, route, feedback, query = build_nodes(
        store,
        classifier_agent,
        feedback_agent,
        query_agent,
    )

    builder = StateGraph(
        SupportState,
        input_schema=SupportInput,
    )

    builder.add_node("initialize", initialize)
    builder.add_node("classifier", classify)
    builder.add_node("feedback", feedback)
    builder.add_node("query", query)

    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "classifier")

    builder.add_conditional_edges(
        "classifier",
        route,
        {
            "feedback": "feedback",
            "query": "query",
            "stop": END,
        },
    )

    builder.add_edge("feedback", END)
    builder.add_edge("query", END)

    return builder.compile(checkpointer=checkpointer)