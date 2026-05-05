from __future__ import annotations

from typing import Any, Dict, Optional

from ..schemas import ArticleBlock


def chroma_filter_from_article_block(
    block: ArticleBlock,
    so_hieu: Optional[str],
) -> Dict[str, Any]:
    """Dict filter cho `ChromaStore.query(where=...)`.
    
    Chroma requires filters to be wrapped in an operator ($and, $or, etc).
    If multiple conditions, wrap in $and.
    """
    conditions: list = []
    
    if so_hieu:
        conditions.append({"so_hieu": so_hieu})
    if block.dieu is not None:
        conditions.append({"dieu": block.dieu})
    if block.khoan is not None:
        conditions.append({"khoan": block.khoan})
    if block.diem:
        conditions.append({"diem": block.diem.strip()})
    if block.phan is not None:
        conditions.append({"phan": block.phan})
    if block.chuong is not None:
        conditions.append({"chuong": block.chuong})
    if block.muc is not None:
        conditions.append({"muc": block.muc})
    
    # Wrap in $and if multiple conditions, or return single condition directly
    if not conditions:
        return {}
    elif len(conditions) == 1:
        return conditions[0]
    else:
        return {"$and": conditions}


def coverage_expected_from_article_block(
    block: ArticleBlock,
    resolved_so_hieu: Optional[str] = None,
) -> Dict[str, Any]:
    """Giá trị cần có trên `chunk.metadata` để coi là đã cover block.

    `so_hieu` trên chunk luôn là mã trong DB/Chroma (vd slug), **không** dùng
    `document_name` trực tiếp. Truyền `resolved_so_hieu` từ
    `search_by_name` / `_resolve_so_hieu` khi block chỉ có tên văn bản.
    """
    req: Dict[str, Any] = {}
    if block.dieu is not None:
        req["dieu"] = block.dieu
    if block.khoan is not None:
        req["khoan"] = block.khoan
    if block.diem:
        req["diem"] = block.diem.strip()
    if block.phan is not None:
        req["phan"] = block.phan
    if block.chuong is not None:
        req["chuong"] = block.chuong
    if block.muc is not None:
        req["muc"] = block.muc
    if block.so_hieu and str(block.so_hieu).strip():
        req["so_hieu"] = str(block.so_hieu).strip()
    elif resolved_so_hieu and str(resolved_so_hieu).strip():
        req["so_hieu"] = str(resolved_so_hieu).strip()
    return req


def coverage_field_matches(expected: Any, actual: Any, field: str) -> bool:
    """So khớp metadata chunk với giá trị từ ArticleBlock (ép kiểu số nếu cần)."""
    if actual is None:
        return False
    if field == "so_hieu":
        return str(actual).strip() == str(expected).strip()
    if field == "diem":
        return str(expected).strip() == str(actual).strip()

    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            if isinstance(expected, int) and int(actual) == expected:
                return True
        except (TypeError, ValueError):
            pass
        try:
            if isinstance(expected, float) and float(actual) == expected:
                return True
        except (TypeError, ValueError):
            pass
    return str(actual) == str(expected)
