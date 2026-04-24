"""
Node: validate_answer (LLM-as-judge)
------------------------------------
Thay cho regex đơn giản, dùng LLM chấm 2 tiêu chí:
- `faithful`: câu trả lời CÓ bám ngữ cảnh (không bịa)?
- `has_citation`: có trích Điều/Khoản/Số hiệu từ ngữ cảnh?
kèm `score` (0–1) và `issues` (list lỗi phát hiện).

Về sources: rút trực tiếp từ metadata của `retrieved_chunks` (vì tool đã
refactor trả structured). Regex chỉ dùng làm fallback cuối cùng.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from ..llms import ask_text
from ..schemas import ValidationResult
from ..graph.state import AgentState

logger = logging.getLogger(__name__)


VALIDATE_SYSTEM_PROMPT = """Bạn là trọng tài chấm chất lượng câu trả lời của hệ thống hỏi đáp pháp luật Việt Nam.
Nhiệm vụ: so sánh câu trả lời với ngữ cảnh được cung cấp, đánh giá 2 tiêu chí:
1. faithful: câu trả lời có CHỈ DỰA trên ngữ cảnh, không bịa không?
2. has_citation: có trích dẫn Điều/Khoản/Số hiệu văn bản xuất hiện trong ngữ cảnh không?

Chỉ trả về JSON HỢP LỆ (không kèm giải thích ngoài JSON), schema:
{
  "faithful": true|false,
  "has_citation": true|false,
  "score": 0.0-1.0,
  "issues": ["..."],
  "reasoning": "tóm tắt ngắn lý do"
}
"""

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")
_SO_HIEU_RE = re.compile(r"\d+/\d{4}(?:/[A-Z0-9\-]+)?")
_CITATION_RES = [
    re.compile(r"\bĐiều\s+\d+", re.IGNORECASE),
    re.compile(r"\bKhoản\s+\d+", re.IGNORECASE),
    _SO_HIEU_RE,
]


def _parse_json(text: str) -> Optional[dict]:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_BLOCK_RE.search(text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _regex_has_citation(text: str) -> bool:
    if not text:
        return False
    return any(r.search(text) for r in _CITATION_RES)


def _extract_sources(chunks: List[Dict[str, Any]]) -> List[str]:
    """Ưu tiên đọc metadata structured; fallback regex trên text."""
    sources: List[str] = []
    seen = set()
    for c in chunks:
        if not isinstance(c, dict):
            continue
        meta = c.get("metadata") or {}
        van_ban = (
            c.get("van_ban")
            or meta.get("van_ban")
            or meta.get("so_hieu")
            or c.get("so_hieu")
        )
        if van_ban and van_ban not in seen:
            seen.add(van_ban)
            sources.append(str(van_ban))
    if sources:
        return sources
    # fallback
    for c in chunks:
        if not isinstance(c, dict):
            continue
        for m in _SO_HIEU_RE.finditer(
            str(c.get("text") or c.get("content") or c.get("display_text") or "")
        ):
            key = m.group(0)
            if key not in seen:
                seen.add(key)
                sources.append(key)
    return sources


def _format_context(chunks: List[Dict[str, Any]], max_chars: int = 4000) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        if not isinstance(c, dict):
            continue
        title = c.get("title") or ""
        text = c.get("text") or c.get("content") or c.get("display_text") or ""
        header = f"[#{i}]" + (f" {title}" if title else "")
        parts.append(f"{header}\n{text}")
    return "\n\n".join(parts)[:max_chars]


def build_validate_node(llm) -> Callable[[AgentState], Dict[str, Any]]:
    """
    Factory: LLM-judge cho validation.
    Nếu LLM fail, fallback về regex heuristic để không chặn pipeline.
    """

    def validate_answer(state: AgentState) -> Dict[str, Any]:
        answer = (state.get("final_answer") or "").strip()
        chunks = state.get("retrieved_chunks", []) or []
        sources = _extract_sources(chunks)

        if not answer:
            result = ValidationResult(
                faithful=False, has_citation=False, score=0.0,
                issues=["empty answer"], reasoning="no answer produced",
            )
            return {"validation": result, "sources": sources}

        # Không có ngữ cảnh → không có gì để "faithful to" — skip LLM cho nhanh
        if not chunks:
            has_cit = _regex_has_citation(answer)
            result = ValidationResult(
                faithful=True, has_citation=has_cit, score=0.5 if has_cit else 0.3,
                issues=[] if has_cit else ["no citation found"],
                reasoning="no retrieved context; regex-only check",
            )
            return {"validation": result, "sources": sources}

        context = _format_context(chunks)
        user_prompt = f"""Câu hỏi của người dùng:
{state.get("original_query") or state.get("query", "")}

Ngữ cảnh đã truy xuất:
{context}

Câu trả lời của hệ thống:
{answer}

Hãy chấm theo schema JSON đã hướng dẫn. CHỈ JSON, không kèm chữ khác."""

        try:
            raw = ask_text(
                llm,
                user_prompt=user_prompt,
                system_prompt=VALIDATE_SYSTEM_PROMPT,
                temperature=0.0,
            )
            parsed = _parse_json(raw)
            if parsed is None:
                raise ValueError(f"cannot parse judge JSON: {raw[:200]}")

            result = ValidationResult(
                faithful=bool(parsed.get("faithful", False)),
                has_citation=bool(parsed.get("has_citation", False)),
                score=float(parsed.get("score", 0.0) or 0.0),
                issues=[str(x) for x in (parsed.get("issues") or [])],
                reasoning=str(parsed.get("reasoning", ""))[:500],
            )
            logger.info(
                "[validate] faithful=%s citation=%s score=%.2f",
                result.faithful, result.has_citation, result.score,
            )
            return {"validation": result, "sources": sources}

        except Exception as e:
            logger.exception("[validate] LLM judge failed, fallback regex")
            has_cit = _regex_has_citation(answer)
            result = ValidationResult(
                faithful=True,  # không kết luận được → không chặn
                has_citation=has_cit,
                score=0.5,
                issues=[f"judge-fallback: {e}"],
                reasoning="LLM judge failed, used regex fallback",
            )
            return {
                "validation": result,
                "sources": sources,
                "errors": [f"validate_answer: {e}"],
            }

    return validate_answer
