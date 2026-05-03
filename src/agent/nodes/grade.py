"""
Node: grade_retrieval (nâng cấp)
--------------------------------
Chiến lược chấm hai tầng:

1. Tầng deterministic (rule-based, rẻ): kiểm tra COVERAGE.
   Nếu `analysis.extracted_blocks` yêu cầu (Điều/Khoản/... cụ thể) mà
   chunks retrieved KHÔNG cover → trả `INSUFFICIENT` ngay, không gọi LLM.

2. Tầng LLM-as-judge: chỉ chạy khi coverage ổn nhưng cần xét ngữ nghĩa.
   LLM chấm 1 trong 3 nhãn: SUFFICIENT | INSUFFICIENT | OFF_TOPIC.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from ..llms import ask_text
from ..schemas import ArticleBlock, Grade, QueryAnalysisResult
from ..graph.state import AgentState
from ..tools import LegalDocumentTools
from ..utils.chroma_metadata import (
    coverage_expected_from_article_block,
    coverage_field_matches,
)
from ..utils.retrieved_context import body_text_for_prompt_item

logger = logging.getLogger(__name__)


GRADE_SYSTEM_PROMPT = """Bạn là trọng tài chấm chất lượng ngữ cảnh cho hệ thống hỏi đáp pháp luật Việt Nam.
Đánh giá ngữ cảnh được cung cấp có đủ thông tin để trả lời câu hỏi không.

Trả lời CHÍNH XÁC một trong ba nhãn (chỉ nhãn, không giải thích):
- SUFFICIENT: đủ thông tin.
- INSUFFICIENT: có liên quan nhưng còn thiếu/mơ hồ, cần tìm thêm.
- OFF_TOPIC: ngữ cảnh không liên quan.
"""


def _parse_grade(text: str) -> Grade:
    t = (text or "").strip().upper()
    first = t.split()[0] if t else ""
    if "OFF_TOPIC" in first or "OFF-TOPIC" in first:
        return Grade.OFF_TOPIC
    if "INSUFFICIENT" in first:
        return Grade.INSUFFICIENT
    if "SUFFICIENT" in first:
        return Grade.SUFFICIENT
    if "OFF_TOPIC" in t or "OFF-TOPIC" in t:
        return Grade.OFF_TOPIC
    if "INSUFFICIENT" in t:
        return Grade.INSUFFICIENT
    return Grade.SUFFICIENT


def _check_coverage(
    analysis: QueryAnalysisResult,
    chunks: List[Dict[str, Any]],
    tools_provider: Optional[LegalDocumentTools] = None,
) -> List[ArticleBlock]:
    """
    Với mỗi block yêu cầu trong analysis.extracted_blocks, kiểm tra có chunk
    nào có metadata trùng khớp (ít nhất các field được yêu cầu).
    Trả về list các block CHƯA được cover.
    """
    if not analysis or not analysis.extracted_blocks:
        return []

    missing: List[ArticleBlock] = []
    for block in analysis.extracted_blocks:
        resolved: Optional[str] = None
        # Bỏ qua _resolve_so_hieu vì không có DB
        if resolved:
            logger.info(
                "[grade] coverage: document_name → so_hieu=%r", resolved
            )
        required = coverage_expected_from_article_block(
            block, resolved_so_hieu=resolved
        )
        if not required:
            continue

        covered = False
        for c in chunks:
            if not isinstance(c, dict):
                continue
            meta_src = c.get("metadata") or c
            ok = True
            for k, v in required.items():
                actual = meta_src.get(k)
                if not coverage_field_matches(v, actual, k):
                    ok = False
                    break
            if ok:
                covered = True
                break
        if not covered:
            missing.append(block)
    return missing


def build_grade_node(
    llm,
    tools_provider: Optional[LegalDocumentTools] = None,
    max_context_chars: int = 3000,
) -> Callable[[AgentState], Dict[str, Any]]:
    def grade_retrieval(state: AgentState) -> Dict[str, Any]:
        chunks = state.get("retrieved_chunks", []) or []
        query = state.get("query", "")
        analysis = state.get("analysis")

        if not chunks:
            logger.info("[grade] no chunks → INSUFFICIENT")
            return {
                "grade": Grade.INSUFFICIENT,
                "grade_reason": "no retrieved chunks",
                "missing_blocks": [],
            }

        # --- Tầng 1: coverage deterministic ---
        missing = (
            _check_coverage(analysis, chunks, tools_provider=tools_provider)
            if analysis
            else []
        )
        if missing:
            reason = "missing blocks: " + ", ".join(
                f"dieu={b.dieu},khoan={b.khoan},diem={b.diem},so_hieu={b.so_hieu or b.document_name}"
                for b in missing
            )
            logger.info("[grade] coverage fail → INSUFFICIENT (%s)", reason)
            return {
                "grade": Grade.INSUFFICIENT,
                "grade_reason": reason,
                "missing_blocks": [b.model_dump() for b in missing],
            }

        # --- Tầng 2: LLM-as-judge về mặt ngữ nghĩa ---
        context_parts: List[str] = []
        for c in chunks:
            text = body_text_for_prompt_item(c) or (
                c.get("text") or c.get("content") or c.get("display_text")
            )
            if text:
                meta = c.get("metadata") or c
                title = meta.get("title") or c.get("title") or ""
                context_parts.append(f"[{title}] {text}" if title else str(text))
        context = "\n---\n".join(context_parts)[:max_context_chars]

        user_prompt = f"""Câu hỏi:
{query}

Ngữ cảnh:
{context}

Nhãn (SUFFICIENT | INSUFFICIENT | OFF_TOPIC):"""

        try:
            resp = ask_text(
                llm,
                user_prompt=user_prompt,
                system_prompt=GRADE_SYSTEM_PROMPT,
                temperature=0.0,
            )
            grade = _parse_grade(resp)
            logger.info("[grade] LLM=%s (raw=%r)", grade, (resp or "")[:80])
            return {
                "grade": grade,
                "grade_reason": (resp or "")[:300],
                "missing_blocks": [],
            }
        except Exception as e:
            logger.exception("[grade] LLM failed, default SUFFICIENT")
            return {
                "grade": Grade.SUFFICIENT,
                "grade_reason": f"grade-fallback: {e}",
                "missing_blocks": [],
                "errors": [f"grade_retrieval: {e}"],
            }

    return grade_retrieval
