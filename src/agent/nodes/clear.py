"""
Node: clear_retrieval
---------------------
Xoá sạch `retrieved_chunks` và `tool_plan` trước khi quay lại `plan_tools`
sau một lần rewrite. Tránh union context với chunks cũ (đã bị grade đánh
là INSUFFICIENT) gây nhiễu cho grade/generate.

Dùng sentinel `RESET_SENTINEL` (xem `state.concat_or_reset`) để vượt qua
reducer operator.add-like mặc định của list.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from ..graph.state import RESET_SENTINEL, AgentState

logger = logging.getLogger(__name__)


def build_clear_retrieval_node() -> Callable[[AgentState], Dict[str, Any]]:
    def clear_retrieval(state: AgentState) -> Dict[str, Any]:
        logger.info("[clear_retrieval] resetting retrieved_chunks & tool_plan")
        return {
            # Gửi sentinel → reducer `concat_or_reset` sẽ xoá sạch
            "retrieved_chunks": [RESET_SENTINEL],
            # tool_plan không có reducer nên ghi đè trực tiếp
            "tool_plan": [],
            # missing_blocks không có reducer, ghi đè về rỗng
            "missing_blocks": [],
        }

    return clear_retrieval
