"""
Node: rewrite_query
-------------------
Chỉ phụ trách viết lại query. Việc xoá `retrieved_chunks` / `tool_results`
do node riêng `clear_retrieval` làm (xem `clear.py`) — tách để code rõ ràng
và dễ test.

Dòng chảy: grade=INSUFFICIENT → rewrite_query → clear_retrieval → plan_tools.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from ..graph.state import AgentState
from ..llms import ask_text

logger = logging.getLogger(__name__)


REWRITE_SYSTEM_PROMPT = """Bạn là trợ lý chuyên viết lại câu hỏi cho hệ thống tìm kiếm pháp luật Việt Nam.
Yêu cầu:
1. Giữ nguyên ý định của người dùng.
2. Mở rộng thuật ngữ pháp lý (ví dụ: "đóng BHYT" → "đóng bảo hiểm y tế, mức đóng, đối tượng tham gia").
3. Thêm đồng nghĩa, tên đầy đủ của văn bản nếu có thể suy ra.
4. KHÔNG thêm thông tin bịa đặt (số điều/khoản không có trong câu gốc).
5. Trả lời CHỈ một câu hỏi đã viết lại, không giải thích, không dấu ngoặc kép.
"""


def build_rewrite_node(llm) -> Callable[[AgentState], Dict[str, Any]]:
    def rewrite_query(state: AgentState) -> Dict[str, Any]:
        original = state.get("original_query") or state.get("query", "")
        current = state.get("query", original)
        count = int(state.get("rewrite_count", 0))
        missing = state.get("missing_blocks") or []
        hint = ""
        if missing:
            hint = (
                "\nCần bổ sung để truy xuất các block pháp lý: "
                + ", ".join(
                    f"(Điều={b.get('dieu')},Khoản={b.get('khoan')},"
                    f"Điểm={b.get('diem')},VB={b.get('document_name')})"
                    for b in missing
                )
            )

        user_prompt = f"""Câu hỏi gốc: {original}
Câu hỏi đang dùng: {current}
Lý do cần viết lại: {state.get("grade_reason") or "ngữ cảnh chưa đủ"}{hint}

Hãy viết lại câu hỏi tìm kiếm:"""

        try:
            new_query = ask_text(
                llm,
                user_prompt=user_prompt,
                system_prompt=REWRITE_SYSTEM_PROMPT,
                temperature=0.2,
            ).strip().strip('"').strip("'")
            if not new_query:
                new_query = current

            logger.info("[rewrite] #%d %r → %r", count + 1, current[:80], new_query[:80])
            return {
                "query": new_query,
                "rewrite_count": count + 1,
            }
        except Exception as e:
            logger.exception("[rewrite] failed")
            return {
                "rewrite_count": count + 1,
                "errors": [f"rewrite_query: {e}"],
            }

    return rewrite_query
