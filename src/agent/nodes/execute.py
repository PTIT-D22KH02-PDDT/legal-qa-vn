"""
Node execute_tool_chain + dispatcher dispatch_tools.

Plan 2 (mức vừa): toàn bộ `tool_plan` chạy **tuần tự** trong một node
(đúng thứ tự LLM planner / router).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List

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


def _invoke_single_task(
    tools_dict: Dict[str, Any],
    tool_name: str,
    tool_input: Dict[str, Any],
    step_num: int,
) -> Dict[str, Any]:
    """Một lần gọi tool → {tool_results, retrieved_chunks, errors?}."""
    logger.info("[execute] tool=%s step=%d", tool_name, step_num)
    if tool_input:
        logger.info("[execute] tool_input=%s", tool_input)
    start = time.time()
    tool = tools_dict.get(tool_name)

    if tool is None:
        step = AgentStep(
            step_number=step_num,
            reasoning=f"Unknown tool: {tool_name}",
            tool_name=tool_name,
            tool_input=tool_input,
            result=ToolExecutionResult(
                tool_name=tool_name,
                success=False,
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

        chunks: List[Dict[str, Any]] = []
        for it in output.items:
            if not isinstance(it, dict):
                continue
            main = {k: v for k, v in it.items() if k != "references"}
            main["_tool"] = tool_name
            main["_step"] = step_num
            main["_role"] = "main"
            chunks.append(main)

            for ref in (it.get("references") or []):
                if not isinstance(ref, dict):
                    continue
                ref_copy = dict(ref)
                ref_copy["_tool"] = tool_name
                ref_copy["_step"] = step_num
                ref_copy["_role"] = "reference"
                ref_copy["_parent_chunk_id"] = main.get("chunk_id")
                chunks.append(ref_copy)

        item_count = len(output.items)
        kinds: Dict[str, int] = {}
        sample_ids: List[str] = []
        for it in output.items:
            if not isinstance(it, dict):
                continue
            kind = str(it.get("kind") or "unknown")
            kinds[kind] = kinds.get(kind, 0) + 1
            cid = it.get("chunk_id") or it.get("id")
            if cid and len(sample_ids) < 3:
                sample_ids.append(str(cid))

        logger.info(
            "[execute] tool=%s items=%d kinds=%s sample_ids=%s",
            tool_name,
            item_count,
            kinds,
            sample_ids,
        )
        if not item_count:
            logger.info(
                "[execute] tool=%s empty output (display_text=%r)",
                tool_name,
                (output.display_text or "")[:200],
            )

        step = AgentStep(
            step_number=step_num,
            reasoning=f"Execute {tool_name}",
            tool_name=tool_name,
            tool_input=tool_input,
            result=ToolExecutionResult(
                tool_name=tool_name,
                success=output.success,
                results=[
                    {
                        "display_text": output.display_text,
                        "item_count": item_count,
                    }
                ],
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
                tool_name=tool_name,
                success=False,
                error=str(e),
                execution_time=elapsed,
            ),
        )
        return {
            "tool_results": [step],
            "errors": [f"execute_tool[{tool_name}]: {e}"],
        }


def build_execute_tool_chain_node(
    tools_provider: LegalDocumentTools,
) -> Callable[[AgentState], Dict[str, Any]]:
    """Chạy lần lượt mọi task trong `tool_plan` (Plan 2)."""
    tools_dict = {t.name: t for t in tools_provider.get_tools_list()}

    def execute_tool_chain(state: AgentState) -> Dict[str, Any]:
        plan: List[ToolTask] = state.get("tool_plan", []) or []
        if not plan:
            return {}

        logger.info("[execute_chain] sequential %d step(s)", len(plan))
        all_steps: List[AgentStep] = []
        all_chunks: List[Dict[str, Any]] = []
        all_errors: List[str] = []

        for task in plan:
            part = _invoke_single_task(
                tools_dict,
                task["tool"],
                task.get("input") or {},
                task.get("step_num", 0),
            )
            all_steps.extend(part.get("tool_results") or [])
            all_chunks.extend(part.get("retrieved_chunks") or [])
            all_errors.extend(part.get("errors") or [])

        out: Dict[str, Any] = {
            "tool_results": all_steps,
            "retrieved_chunks": all_chunks,
        }
        if all_errors:
            out["errors"] = all_errors
        return out

    return execute_tool_chain


def dispatch_tools(state: AgentState):
    """Conditional edge: có plan → node chuỗi; không → generate."""
    plan: List[ToolTask] = state.get("tool_plan", []) or []
    if not plan:
        logger.info("[dispatch] empty plan → generate_answer")
        return "generate_answer"

    logger.info("[dispatch] sequential chain %d tool(s)", len(plan))
    return "execute_tool_chain"
