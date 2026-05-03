"""
Chuỗi nội dung đưa vào prompt (generate/validate) từ từng item trong
`retrieved_chunks` — cả chunk RAG lẫn dòng từ `search_document_metadata`.
"""

from __future__ import annotations

from typing import Any, Dict


def body_text_for_prompt_item(c: Dict[str, Any]) -> str:
    """Nội dung “thân” block cho LLM: chunk có text, metadata có trường ngày/loại."""
    if c.get("kind") == "metadata":
        parts: list[str] = []
        for key, label in (
            ("ten_van_ban", "Tên văn bản"),
            ("loai", "Loại văn bản"),
            ("co_quan_ban_hanh", "Cơ quan ban hành"),
            ("ngay_ban_hanh", "Ngày ban hành"),
            ("ngay_co_hieu_luc", "Ngày có hiệu lực"),
        ):
            v = c.get(key)
            if v not in (None, ""):
                parts.append(f"{label}: {v}")
        if c.get("so_dieu") not in (None, 0, ""):
            parts.append(f"Số điều (gợi ý từ DB): {c.get('so_dieu')}")
        if parts:
            return "\n".join(parts)
    return (c.get("text") or c.get("content") or c.get("display_text") or "").strip()
