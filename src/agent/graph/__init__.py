"""
LangGraph-based Legal QA Agent.

Cách dùng nhanh (từ runner):

    from src.agent.graph import build_default_graph
    graph = build_default_graph(llm, tools_provider)
    result = graph.invoke(
        {"query": "Điều 5 của Luật 102/2017 nói gì?"},
        config={"configurable": {"thread_id": "user-1"}},
    )
    print(result["final_answer"])
    print(result.get("sources"))
"""

from .builder import build_default_graph, build_graph
from .state import MAX_REWRITES, AgentState, ToolTask

__all__ = [
    "build_graph",
    "build_default_graph",
    "AgentState",
    "ToolTask",
    "MAX_REWRITES",
]
