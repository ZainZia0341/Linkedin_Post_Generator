from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.conditional_edges import (
    route_after_memory,
    route_after_research,
    route_after_review,
    route_guardrail_decision,
)
from app.graph_state_schema import GraphState
from app.nodes.guardrail_node import guardrail_node, hardcoded_guardrail_node
from app.nodes.memory_check_node import delete_messages
from app.nodes.post_nodes import (
    generate_post_node,
    modify_post_node,
    review_post_node,
    web_research_node,
)


def build_post_graph():
    graph = StateGraph(GraphState)
    graph.add_node("memory_checker", delete_messages)
    graph.add_node("web_research", web_research_node)
    graph.add_node("generate_post", generate_post_node)
    graph.add_node("guardrail", guardrail_node)
    graph.add_node("hardcoded_guardrail", hardcoded_guardrail_node)
    graph.add_node("modify_post", modify_post_node)
    graph.add_node("review_post", review_post_node)

    graph.add_edge(START, "memory_checker")
    graph.add_conditional_edges(
        "memory_checker",
        route_after_memory,
        {
            "web_research": "web_research",
            "guardrail": "guardrail",
        },
    )
    graph.add_conditional_edges(
        "web_research",
        route_after_research,
        {
            "generate_post": "generate_post",
            "modify_post": "modify_post",
        },
    )
    graph.add_edge("generate_post", "review_post")
    graph.add_conditional_edges(
        "guardrail",
        route_guardrail_decision,
        {
            "web_research": "web_research",
            "hardcoded_guardrail": "hardcoded_guardrail",
        },
    )
    graph.add_edge("hardcoded_guardrail", END)
    graph.add_edge("modify_post", "review_post")
    graph.add_conditional_edges(
        "review_post",
        route_after_review,
        {
            "retry_generate": "generate_post",
            "retry_modify": "modify_post",
            "done": END,
        },
    )
    return graph.compile()


def run_post_generation(state: GraphState) -> GraphState:
    print("Starting post generation graph.")
    graph = build_post_graph()
    return graph.invoke({**state, "workflow_mode": "generate"})


def run_post_chat_edit(state: GraphState) -> GraphState:
    print("Starting post edit graph.")
    graph = build_post_graph()
    return graph.invoke({**state, "workflow_mode": "chat"})
