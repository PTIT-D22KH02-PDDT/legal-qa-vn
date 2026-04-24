"""
Node: plan_tools.

Bọc `ToolRouter` để chuyển `QueryAnalysisResult` thành danh sách `ToolTask`.
Router đã chứa đầy đủ logic short-circuit (in_scope, is_specific, intent=CALCULATE,
v.v.) nên node này chỉ lo I/O với state.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from ..graph.state import AgentState, ToolTask
from ..router import ToolRouter

logger = logging.getLogger(__name__)


def build_plan_node() -> Callable[[AgentState], Dict[str, Any]]:
    router = ToolRouter()

    def plan_tools(state: AgentState) -> Dict[str, Any]:
        analysis = state.get("analysis")
        if analysis is None:
            logger.warning("[plan] no analysis → empty plan")
            return {"tool_plan": []}

        tool_calls = router.route(analysis)  # List[Tuple[str, dict]]
        plan: List[ToolTask] = [
            {"tool": name, "input": inp, "step_num": idx + 1}
            for idx, (name, inp) in enumerate(tool_calls)
        ]

        logger.info("[plan] tasks=%s", [p["tool"] for p in plan])
        return {"tool_plan": plan}

    return plan_tools
