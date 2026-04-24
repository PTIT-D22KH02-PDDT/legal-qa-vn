"""
Node execute_tool + dispatcher dispatch_tools.

Mỗi instance `execute_tool` được spawn qua `Send` (fan-out parallel).
Kết quả (structured) được nối vào `tool_results` + `retrieved_chunks` nhờ
reducer khai báo ở `state.py`.

Tool nay trả về `ToolOutput` (Pydantic) thay vì string, nên node này
giữ nguyên metadata xuống các node grade / generate / validate.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List

from langgraph.constants import Send

from ..schemas import AgentStep, ToolExecutionResult, ToolOutput
from ..tools import LegalDocumentTools
from ..graph.state import AgentState, ToolTask

logger = logging.getLogger(__name__)


def _coerce_to_tool_output(raw: Any, tool_name: str) -> ToolOutput:
    """Phòng thủ: nếu tool (hoặc legacy) trả dict/str, ép về ToolOutput."""
    if isinstance(raw, ToolOutput):
        return raw
    if isinstance(raw, dict):
        try:
            return ToolOutput(**{"tool_name": tool_name, **raw})
        except Exception:
            pass
    text = raw if isinstance(raw, str) else str(raw)
    return ToolOutput(
        tool_name=tool_name,
        success=bool(text) and "Lỗi" not in text and "không tìm thấy" not in text.lower(),
        display_text=text,
        items=[],
    )


def build_execute_node(
    tools_provider: LegalDocumentTools,
) -> Callable[[ToolTask], Dict[str, Any]]:
    """Factory tạo node `execute_tool`."""
    tools_dict = {t.name: t for t in tools_provider.get_tools_list()}

    def execute_tool(task: ToolTask) -> Dict[str, Any]:
        tool_name = task["tool"]
        tool_input = task.get("input") or {}
        step_num = task.get("step_num", 0)

        logger.info("[execute] tool=%s step=%d", tool_name, step_num)

        start = time.time()
        tool = tools_dict.get(tool_name)

        if tool is None:
            step = AgentStep(
                step_number=step_num,
                reasoning=f"Unknown tool: {tool_name}",
                tool_name=tool_name,
                tool_input=tool_input,
                result=ToolExecutionResult(
                    tool_name=tool_name, success=False,
                    error="unknown tool",
                    execution_time=time.time() - start,
                ),
            )
            return {
                "tool_results": [step],
                "errors": [f"execute_tool: unknown tool {tool_name}"],
            }

        try:
            raw = tool.invoke(tool_input)
            output = _coerce_to_tool_output(raw, tool_name)
            elapsed = time.time() - start

            # Bắn structured items vào retrieved_chunks (giữ metadata đầy đủ)
            chunks: List[Dict[str, Any]] = []
            for it in output.items:
                if isinstance(it, dict):
                    enriched = {**it, "_tool": tool_name, "_step": step_num}
                    chunks.append(enriched)

            step = AgentStep(
                step_number=step_num,
                reasoning=f"Execute {tool_name}",
                tool_name=tool_name,
                tool_input=tool_input,
                result=ToolExecutionResult(
                    tool_name=tool_name,
                    success=output.success,
                    results=[{
                        "display_text": output.display_text,
                        "item_count": len(output.items),
                    }],
                    error=output.error,
                    execution_time=elapsed,
                ),
            )
            return {
                "tool_results": [step],
                "retrieved_chunks": chunks,
            }

        except Exception as e:
            elapsed = time.time() - start
            logger.exception("[execute] tool=%s failed", tool_name)
            step = AgentStep(
                step_number=step_num,
                reasoning=f"Execute {tool_name}",
                tool_name=tool_name,
                tool_input=tool_input,
                result=ToolExecutionResult(
                    tool_name=tool_name, success=False,
                    error=str(e), execution_time=elapsed,
                ),
            )
            return {
                "tool_results": [step],
                "errors": [f"execute_tool[{tool_name}]: {e}"],
            }

    return execute_tool


def dispatch_tools(state: AgentState):
    """Conditional edge: fan-out qua `Send` hoặc skip sang generate."""
    plan: List[ToolTask] = state.get("tool_plan", []) or []
    if not plan:
        logger.info("[dispatch] empty plan → generate_answer")
        return "generate_answer"

    logger.info("[dispatch] fan-out %d tool(s)", len(plan))
    return [Send("execute_tool", task) for task in plan]
