"""
Build & compile LangGraph cho Legal QA Agent.

Topology:

    START ──► analyze_query ──► plan_tools ──(dispatch_tools)──►
        ├── execute_tool  (fan-out parallel qua Send)
        │      └──► grade_retrieval ──(route_after_grade)──►
        │               ├── rewrite_query ──► clear_retrieval ──► plan_tools
        │               │      (loop, ≤ MAX_REWRITES)
        │               └── generate_answer ──► validate_answer ──► END
        └── generate_answer (khi plan rỗng)
                └──► validate_answer ──► END

Thay đổi vs. phiên bản đầu:
- Có node `clear_retrieval` giữa `rewrite_query` và `plan_tools` để xoá
  sạch chunks cũ (dùng custom reducer + sentinel).
- `validate_answer` dùng LLM-as-judge (kèm regex fallback) → cần truyền llm.
- Hỗ trợ SqliteSaver cho checkpointer bền vững.
"""

from __future__ import annotations

import logging
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from langchain_core.language_models import BaseChatModel

from ..tools import LegalDocumentTools
from ..nodes import (
    build_analyze_node,
    build_clear_retrieval_node,
    build_execute_node,
    build_generate_node,
    build_grade_node,
    build_plan_node,
    build_rewrite_node,
    build_validate_node,
    dispatch_tools,
)
from .edges import route_after_grade
from .state import AgentState

logger = logging.getLogger(__name__)


def build_graph(
    llm: BaseChatModel,
    tools_provider: LegalDocumentTools,
    checkpointer: Optional[object] = None,
):
    """
    Dựng & compile graph.

    Args:
        llm: LLM dùng chung cho analyze / grade / rewrite / generate / validate.
        tools_provider: `LegalDocumentTools` đã có sẵn chroma_store + embedding.
        checkpointer: `MemorySaver()`, `SqliteSaver(...)` hoặc None.

    Returns:
        CompiledGraph — gọi `.invoke({"query": "..."})` hoặc `.stream(...)`.
    """
    g = StateGraph(AgentState)

    g.add_node("analyze_query", build_analyze_node(llm))
    g.add_node("plan_tools", build_plan_node())
    g.add_node("execute_tool", build_execute_node(tools_provider))
    g.add_node("grade_retrieval", build_grade_node(llm))
    g.add_node("rewrite_query", build_rewrite_node(llm))
    g.add_node("clear_retrieval", build_clear_retrieval_node())
    g.add_node("generate_answer", build_generate_node(llm))
    g.add_node("validate_answer", build_validate_node(llm))

    g.add_edge(START, "analyze_query")
    g.add_edge("analyze_query", "plan_tools")

    g.add_conditional_edges(
        "plan_tools",
        dispatch_tools,
        ["execute_tool", "generate_answer"],
    )
    g.add_edge("execute_tool", "grade_retrieval")

    g.add_conditional_edges(
        "grade_retrieval",
        route_after_grade,
        {
            "generate_answer": "generate_answer",
            "rewrite_query": "rewrite_query",
        },
    )

    # Rewrite → clear → quay lại plan_tools (loop, guard bởi rewrite_count)
    g.add_edge("rewrite_query", "clear_retrieval")
    g.add_edge("clear_retrieval", "plan_tools")

    g.add_edge("generate_answer", "validate_answer")
    g.add_edge("validate_answer", END)

    compiled = g.compile(checkpointer=checkpointer)
    logger.info("[graph] compiled successfully")
    return compiled


def _make_sqlite_saver(db_path: str):
    """
    Tạo SqliteSaver. Import trễ để repo không bắt buộc cài sqlite extra khi
    chỉ chạy MemorySaver. Yêu cầu: `pip install langgraph-checkpoint-sqlite`.
    """
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore
    except ImportError as e:
        raise ImportError(
            "SqliteSaver không có sẵn. Cài thêm: "
            "`pip install langgraph-checkpoint-sqlite`"
        ) from e
    return SqliteSaver.from_conn_string(db_path)


def build_default_graph(
    llm: BaseChatModel,
    tools_provider: LegalDocumentTools,
    checkpointer_kind: str = "memory",  # "memory" | "sqlite" | "none"
    sqlite_path: str = "agent_checkpoints.sqlite",
):
    """
    Convenience wrapper.

    Args:
        checkpointer_kind:
            - "memory": MemorySaver (RAM, mặc định, tốt cho dev).
            - "sqlite": SqliteSaver ghi xuống file — bền qua restart.
            - "none":  không checkpoint (không hỗ trợ multi-turn state).
        sqlite_path: đường dẫn file SQLite khi chọn "sqlite".
    """
    kind = (checkpointer_kind or "memory").lower()
    if kind == "memory":
        checkpointer = MemorySaver()
    elif kind == "sqlite":
        checkpointer = _make_sqlite_saver(sqlite_path)
    elif kind == "none":
        checkpointer = None
    else:
        raise ValueError(f"Unknown checkpointer_kind: {checkpointer_kind}")

    return build_graph(llm, tools_provider, checkpointer=checkpointer)
