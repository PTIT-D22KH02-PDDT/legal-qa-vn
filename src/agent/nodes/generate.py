"""
Node: generate_answer
---------------------
LLM thuần (không bind tool). Đọc `retrieved_chunks` đã structured, tự tạo
block context có tiêu đề rõ ràng (Điều/Khoản/Số hiệu) để LLM trích dẫn
chính xác hơn.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from ..llms import ask_text
from ..schemas import Grade
from ..graph.state import AgentState

logger = logging.getLogger(__name__)


ANSWER_SYSTEM_PROMPT = """Bạn là trợ lý pháp lý Việt Nam. Trả lời dựa HOÀN TOÀN trên ngữ cảnh được cung cấp.
Nguyên tắc bắt buộc:
1. Luôn trích dẫn nguồn cụ thể (Điều, Khoản, Số hiệu văn bản) nếu ngữ cảnh có.
2. Nếu ngữ cảnh KHÔNG đủ, hãy nói rõ: "Tôi chưa đủ thông tin để trả lời chắc chắn."
3. KHÔNG suy diễn, KHÔNG bịa điều khoản không xuất hiện trong ngữ cảnh.
4. Trình bày rõ ràng, có đánh số nếu nhiều ý.
5. Văn phong trung tính, dễ hiểu.
"""

FALLBACK_NO_CONTEXT = (
    "Tôi chưa tìm thấy điều khoản pháp luật phù hợp để trả lời câu hỏi của bạn. "
    "Bạn có thể cung cấp thêm chi tiết (tên văn bản, số hiệu, điều/khoản cụ thể) "
    "để mình tìm chính xác hơn không?"
)

FALLBACK_OFF_TOPIC = (
    "Câu hỏi của bạn có vẻ nằm ngoài phạm vi dữ liệu pháp luật mình đang có. "
    "Mình chỉ hỗ trợ tra cứu văn bản quy phạm pháp luật Việt Nam."
)


def _format_context(chunks: List[Dict[str, Any]], max_chars: int = 6000) -> str:
    """Format chunks có metadata thành block rõ ràng."""
    parts = []
    for i, c in enumerate(chunks, 1):
        if not isinstance(c, dict):
            continue
        title = c.get("title") or ""
        van_ban = c.get("van_ban") or (c.get("metadata") or {}).get("van_ban") or ""
        text = c.get("text") or c.get("content") or c.get("display_text") or ""
        header = f"[#{i}]"
        if title:
            header += f" {title}"
        if van_ban and van_ban not in header:
            header += f" (Nguồn: {van_ban})"
        parts.append(f"{header}\n{text}")
    joined = "\n\n".join(parts)
    return joined[:max_chars]


def build_generate_node(llm) -> Callable[[AgentState], Dict[str, Any]]:
    def generate_answer(state: AgentState) -> Dict[str, Any]:
        query = state.get("original_query") or state.get("query", "")
        chunks = state.get("retrieved_chunks", []) or []
        grade = state.get("grade")

        if grade == Grade.OFF_TOPIC:
            logger.info("[generate] grade=OFF_TOPIC → fallback")
            return {"final_answer": FALLBACK_OFF_TOPIC}

        if not chunks:
            logger.info("[generate] no chunks → fallback no-context")
            return {"final_answer": FALLBACK_NO_CONTEXT}

        context = _format_context(chunks)

        user_prompt = f"""Câu hỏi: {query}

Ngữ cảnh tham khảo:
{context}

Hãy trả lời câu hỏi dựa trên ngữ cảnh ở trên. Nhớ trích dẫn Điều/Khoản/Số hiệu."""

        try:
            answer = ask_text(
                llm,
                user_prompt=user_prompt,
                system_prompt=ANSWER_SYSTEM_PROMPT,
                temperature=0.2,
            )
            logger.info("[generate] answer len=%d", len(answer or ""))
            return {"final_answer": (answer or "").strip()}
        except Exception as e:
            logger.exception("[generate] failed")
            return {
                "final_answer": f"Lỗi sinh câu trả lời: {e}",
                "errors": [f"generate_answer: {e}"],
            }

    return generate_answer
