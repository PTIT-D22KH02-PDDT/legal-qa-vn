"""
AgentState cho LangGraph của Legal QA Agent.

Điểm quan trọng:
- Các field list dùng *reducer* để LangGraph biết cách merge khi nhiều node
  (đặc biệt là `execute_tool` fan-out qua `Send`) cùng ghi vào.
- `retrieved_chunks` dùng reducer tuỳ biến `concat_or_reset` để `clear_retrieval`
  có thể xoá sạch state này trước khi loop lại (sau rewrite_query).
- `total=False` cho phép partial update từ mỗi node.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from ..schemas import AgentStep, Grade, QueryAnalysisResult, ValidationResult


RESET_SENTINEL = "__RESET__"
"""Sentinel gửi kèm vào list reducer để yêu cầu xoá sạch field."""


def concat_or_reset(left: List[Any], right: List[Any]) -> List[Any]:
    """
    Reducer cho list có hỗ trợ reset.

    - Nếu `right` là list bắt đầu bằng `RESET_SENTINEL`, trả về phần còn lại
      của `right` (bỏ sentinel), bỏ qua `left` cũ.
    - Ngược lại nối `left + right` như `operator.add`.
    """
    if left is None:
        left = []
    if right is None:
        right = []
    if not isinstance(right, list):
        right = [right]
    if right and right[0] == RESET_SENTINEL:
        return right[1:]
    return left + right


class ToolTask(TypedDict, total=False):
    """Một đơn vị công việc tool được plan_tools sinh ra."""
    tool: str
    input: Dict[str, Any]
    step_num: int


class AgentState(TypedDict, total=False):
    # ---------- Input ----------
    query: str
    original_query: str
    messages: Annotated[List[AnyMessage], add_messages]

    # ---------- Stage: Analyze ----------
    analysis: Optional[QueryAnalysisResult]

    # ---------- Stage: Plan ----------
    tool_plan: List[ToolTask]

    # ---------- Stage: Execute (fan-out) ----------
    tool_results: Annotated[List[AgentStep], operator.add]
    retrieved_chunks: Annotated[List[Dict[str, Any]], concat_or_reset]

    # ---------- Stage: Grade / Rewrite ----------
    grade: Optional[Grade]
    grade_reason: Optional[str]
    missing_blocks: List[Dict[str, Any]]
    rewrite_count: int

    # ---------- Stage: Generate / Validate ----------
    final_answer: Optional[str]
    sources: List[str]
    validation: Optional[ValidationResult]

    # ---------- Error accumulator ----------
    errors: Annotated[List[str], operator.add]


MAX_REWRITES: int = 2
MAX_TOOL_PARALLEL: int = 4
