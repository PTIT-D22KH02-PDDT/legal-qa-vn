"""
Node: plan_tools.

- Mặc định (Plan 2): LLM planner sinh chuỗi tool; fallback `ToolRouter` nếu lỗi/rỗng.
- Tắt `planner.enabled` trong config: chỉ dùng `ToolRouter` như cũ.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Tuple

from langchain_core.language_models import BaseChatModel

from ..graph.state import AgentState, ToolTask
from ..llm_planner import build_tool_plan_from_llm
from ..router import ToolRouter
from ..schemas import Intent

logger = logging.getLogger(__name__)

DEFAULT_PLANNER = {"enabled": True, "max_steps": 6}


def build_plan_node(
    llm: BaseChatModel,
    planner_config: Dict[str, Any] | None = None,
) -> Callable[[AgentState], Dict[str, Any]]:
    router = ToolRouter()
    pconf = {**DEFAULT_PLANNER, **(planner_config or {})}
    use_llm = bool(pconf.get("enabled", True))
    max_steps = int(pconf.get("max_steps", 6))

    def plan_tools(state: AgentState) -> Dict[str, Any]:
        analysis = state.get("analysis")
        if analysis is None:
            logger.warning("[plan] no analysis → empty plan")
            return {"tool_plan": []}

        router_calls: List[Tuple[str, Dict[str, Any]]] = router.route(analysis)
        if router_calls:
            logger.info(
                "[plan] router_calls=%s",
                [{"tool": n, "input": i} for n, i in router_calls],
            )
        tool_calls: List[Tuple[str, Dict[str, Any]]] = list(router_calls)

        if use_llm and analysis.in_scope and analysis.intent != Intent.CALCULATE:
            try:
                q = state.get("original_query") or state.get("query", "")
                planned = build_tool_plan_from_llm(
                    llm, q, analysis, router_calls, max_steps=max_steps
                )
                if planned:
                    tool_calls = planned
                    logger.info(
                        "[plan] llm_plan=%s",
                        [{"tool": n, "input": i} for n, i in planned],
                    )
            except Exception as e:
                logger.warning("[plan] LLM planner failed, use router: %s", e)

        plan: List[ToolTask] = [
            {"tool": name, "input": inp, "step_num": idx + 1}
            for idx, (name, inp) in enumerate(tool_calls)
        ]

        logger.info("[plan] tasks=%s", [p["tool"] for p in plan])
        return {"tool_plan": plan}

    return plan_tools
