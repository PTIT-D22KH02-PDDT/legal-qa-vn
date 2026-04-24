"""
Conditional edge functions cho LangGraph.

Tách riêng để builder.py gọn và dễ test.
"""

from __future__ import annotations

import logging

from ..schemas import Grade
from .state import MAX_REWRITES, AgentState

logger = logging.getLogger(__name__)


def route_after_grade(state: AgentState) -> str:
    """
    Sau khi grade:
    - SUFFICIENT     → generate_answer
    - OFF_TOPIC      → generate_answer (sẽ trả fallback)
    - INSUFFICIENT   → nếu còn quota rewrite → rewrite_query, else generate_answer
    """
    grade = state.get("grade")
    rewrite_count = int(state.get("rewrite_count", 0))

    if grade == Grade.SUFFICIENT:
        return "generate_answer"

    if grade == Grade.OFF_TOPIC:
        return "generate_answer"

    if rewrite_count < MAX_REWRITES:
        logger.info(
            "[edge] grade=%s, rewrite %d/%d → rewrite_query",
            grade, rewrite_count + 1, MAX_REWRITES,
        )
        return "rewrite_query"

    logger.info("[edge] rewrite quota exhausted → generate_answer")
    return "generate_answer"
