"""
Plan 2 (mức vừa): LLM sinh danh sách bước (tool + input) từ phân tích câu hỏi.
Fallback: gợi ý từ ToolRouter nếu parse lỗi / rỗng.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.language_models import BaseChatModel

from .llms import ask_text
from .schemas import QueryAnalysisResult

logger = logging.getLogger(__name__)

ALLOWED_TOOLS: frozenset = frozenset(
    {
        "search_legal_documents",
        "search_document_metadata",
        "get_specific_article",
        "find_related_documents",
        "find_cross_references",
    }
)

PLANNER_SYSTEM = """Bạn là bộ lập kế hoạch gọi công cụ cho hệ thống tra cứu pháp luật VN.
Nhiệm vụ: chọn THỨ TỰ các tool và tham số, JSON duy nhất, không markdown.

Công cụ (tên gọi chính xác):
1) search_document_metadata — truy vấn bảng metadata tài liệu (số hiệu, tên, ngày ban hành, ngày có hiệu lực, loại, cơ quan).
   Input: { "so_hieu": str|null, "ten_van_ban": str|null, "doc_type": str|null, "org_unit": str|null, "limit": int } (các trường tùy chọn, truyền cái đã rõ từ câu hỏi/entity).
2) search_legal_documents — tìm chunk điều/khoản/điểm (RAG, vector).
   Input: { "query": str, "top_k": int, "include_references": bool } — filter mặc định hệ thống.
3) get_specific_article — nội dung đúng Điều/Khoản/Điểm khi biết số. Có thể kèm
   "include_references": true (mặc định) để tải thêm nội dung chunk trong metadata.reference.
   Input: { "article_block": { ... }, "include_references": bool }
4) find_related_documents — sửa đổi/bổ sung/thay thế/liên quan theo so_hieu văn bản.
   Input: { "doc_id": str, "relation_type": str|null }
5) find_cross_references — tham chiếu chéo giữa chunk.
   Input: { "article_block": { ... } } hoặc { "chunk_id": str }.

Quy tắc:
- Câu hỏi về *thời điểm ban hành, có hiệu lực, tên số hiệu văn bản* → ưu tiên bước `search_document_metadata` (có thể dùng ten_van_ban) TRƯỚC, sau đó mới tới RAG nếu còn cần nội dung điều khoản.
- Câu hỏi “Điều X nói gì / khoản Y” với tên văn bản rõ → có thể `get_specific_article` (article_block từ extracted_blocks).
- Câu tổng quát / tìm hiểu chung → `search_legal_documents`.
- Nhiều bước: tối đa theo max_steps, thứ tự từ trên xuống; sau metadata có thể thêm RAG cùng tên văn bản trong query nếu cần.

Chỉ trả về:
{"steps": [ {"tool": "<tên>", "input": { ... } }, ... ]}
Không thêm trường ngoài "steps"."""


def _json_safe(obj: Any) -> Any:
    """Pydantic model / lồng dict-list → types JSON hợp lệ (cho json.dumps)."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if hasattr(obj, "model_dump"):
        try:
            return _json_safe(obj.model_dump(mode="json"))
        except Exception:
            return _json_safe(getattr(obj, "model_dump", lambda: {})())
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return str(obj)


def _json_from_text(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _normalize_steps(
    raw: Any, max_steps: int,
) -> List[Tuple[str, Dict[str, Any]]]:
    if not isinstance(raw, dict):
        return []
    steps = raw.get("steps")
    if not isinstance(steps, list):
        return []
    out: List[Tuple[str, Dict[str, Any]]] = []
    for s in steps[: max(0, max_steps)]:
        if not isinstance(s, dict):
            continue
        name = s.get("tool")
        if not isinstance(name, str) or name not in ALLOWED_TOOLS:
            continue
        inp = s.get("input")
        if not isinstance(inp, dict):
            inp = {}
        out.append((name, dict(inp)))
    return out


def build_tool_plan_from_llm(
    llm: BaseChatModel,
    original_query: str,
    analysis: QueryAnalysisResult,
    router_steps: List[Tuple[str, Dict[str, Any]]],
    max_steps: int = 6,
) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Gọi LLM để sinh chuỗi tool. `router_steps` = fallback + context trong prompt.
    Trả về list rỗng nếu cần caller fallback router.
    """
    try:
        a_dump = _json_safe(analysis)
    except Exception as e:
        logger.warning("[llm_planner] could not prepare analysis: %s", e)
        a_dump = str(analysis)

    hint = [
        {"tool": n, "input": _json_safe(i)} for n, i in (router_steps or [])
    ]
    user = f"""Câu hỏi (nguyên bản):
{original_query}

Phân tích (JSON):
{json.dumps(a_dump, ensure_ascii=False, indent=2)}

Gợi ý từ router tham khảo (có thể sửa/cải thêm bước, đặc biệt metadata trước RAG nếu câu hỏi về ngày/số hiệu):
{json.dumps(hint, ensure_ascii=False, indent=2)}

Trả về duy nhất object JSON theo schema đã dặn.
"""
    try:
        raw = ask_text(
            llm, user_prompt=user, system_prompt=PLANNER_SYSTEM, temperature=0.0
        )
    except Exception as e:
        logger.warning("[llm_planner] ask_text failed: %s", e)
        return []
    data = _json_from_text(raw or "")
    steps = _normalize_steps(data, max_steps=max_steps)
    if not steps:
        logger.info("[llm_planner] empty/invalid plan from LLM → fallback to router")
    else:
        logger.info("[llm_planner] plan=%s", [s[0] for s in steps])
        logger.info("[llm_planner] LLM raw response=%s", raw[:500] if raw else "empty")
        for idx, (tool_name, tool_input) in enumerate(steps):
            logger.info(
                "[llm_planner] step[%d] tool=%s input=%s",
                idx, tool_name, tool_input
            )
    return steps
