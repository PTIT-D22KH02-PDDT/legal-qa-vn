"""
ToolRouter — chuyển QueryAnalysisResult thành danh sách tool calls.

Triết lý mới (sau khi schema đơn giản còn `in_scope` + `is_specific`):

1. Nếu `in_scope=False`         → trả [] → graph sẽ short-circuit sang generate
                                  để trả fallback "ngoài phạm vi".
2. Nếu `intent = CALCULATE`      → trả [] → LLM tự tính, không cần tool.
3. Nếu `is_specific` + có blocks → 1 call `get_specific_article` / block có
                                   `dieu`. Không kèm `search_legal_documents`
                                   để tránh nhiễu.
4. Ngược lại (general)           → `search_legal_documents` (semantic).
5. Bổ sung: (Hiện tại đã vô hiệu hóa do không còn dùng Database)
   - search_document_metadata (disabled)
   - find_related_documents (disabled)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from .schemas import ArticleBlock, Intent, QueryAnalysisResult

logger = logging.getLogger(__name__)


class ToolRouter:
    """Router tool dựa trên `QueryAnalysisResult`."""

    DEFAULT_TOP_K: int = 5
    DEFAULT_FILTER_TYPES: List[str] = ["dieu", "khoan", "diem"]

    def route(
        self, analysis: QueryAnalysisResult,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        logger.info(
            "[router] in_scope=%s specific=%s blocks=%d intent=%s",
            analysis.in_scope, analysis.is_specific,
            len(analysis.extracted_blocks), analysis.intent,
        )

        # 1. Out of scope → không gọi tool
        if not analysis.in_scope:
            logger.info("[router] out of scope → skip all tools")
            return []

        # 2. Calculate → để LLM tự làm
        if analysis.intent == Intent.CALCULATE:
            logger.info("[router] intent=CALCULATE → skip tools")
            return []

        tool_calls: List[Tuple[str, Dict[str, Any]]] = []

        # 3. Specific article lookup: 1 call/block có `dieu`
        if analysis.is_specific and analysis.extracted_blocks:
            for block in analysis.extracted_blocks:
                if block.dieu is not None:
                    tool_calls.append(
                        ("get_specific_article", {"article_block": block})
                    )

        # 4. Nếu CHƯA có specific call nào → cần search semantic
        if not tool_calls:
            tool_calls.append((
                "search_legal_documents",
                {
                    "query": analysis.original_query,
                    "top_k": self.DEFAULT_TOP_K,
                    "filter_by_type": list(self.DEFAULT_FILTER_TYPES),
                },
            ))

        # 5. (Bỏ qua metadata search và relationship check vì không có DB)
        
        logger.info("[router] tools=%s", [t[0] for t in tool_calls])
        return tool_calls

    # ------------------------------------------------------------------
    def get_tool_explanation(self, tool_name: str) -> str:
        explanations = {
            "search_legal_documents": "Tìm kiếm tài liệu bằng vector similarity",
            "get_specific_article": "Lấy nội dung điều khoản cụ thể",
            "find_cross_references": "Tìm các tham chiếu chéo",
        }
        return explanations.get(tool_name, "Tool không xác định")


def _first_doc_identifier(blocks: List[ArticleBlock]) -> str | None:
    """Ưu tiên số hiệu; fallback tên văn bản."""
    for b in blocks:
        if b.so_hieu:
            return b.so_hieu
    for b in blocks:
        if b.document_name:
            return b.document_name
    return None
