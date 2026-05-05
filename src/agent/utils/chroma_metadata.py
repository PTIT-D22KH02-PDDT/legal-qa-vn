from __future__ import annotations

from typing import Any, Dict, Optional
from ..schemas import ArticleBlock
from src.indexing.embedding.utils import SECTION_TYPE_NAMES

def _normalize_with_prefix(value: Any, section_type: str) -> str:
    """Đảm bảo giá trị có tiền tố đúng (ví dụ: '1' -> 'Điều 1')."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    
    prefix = SECTION_TYPE_NAMES.get(section_type, "")
    if prefix and not s.startswith(prefix):
        return f"{prefix} {s}"
    return s

def chroma_filter_from_article_block(
    block: ArticleBlock,
    so_hieu: Optional[str],
) -> Dict[str, Any]:
    """Dict filter cho `ChromaStore.query(where=...)`."""
    out: Dict[str, Any] = {}
    if so_hieu:
        out["so_hieu"] = so_hieu
    
    # Ép kiểu có tiền tố để khớp với dữ liệu trong ChromaDB (Điều 1, Khoản 2...)
    if block.dieu:
        out["dieu"] = _normalize_with_prefix(block.dieu, "dieu")
    if block.khoan:
        out["khoan"] = _normalize_with_prefix(block.khoan, "khoan")
    if block.diem:
        out["diem"] = _normalize_with_prefix(block.diem, "diem")
    if block.phan:
        out["phan"] = _normalize_with_prefix(block.phan, "phan")
    if block.chuong:
        out["chuong"] = _normalize_with_prefix(block.chuong, "chuong")
    if block.muc:
        out["muc"] = _normalize_with_prefix(block.muc, "muc")
        
    return {k: v for k, v in out.items() if v}


def coverage_expected_from_article_block(
    block: ArticleBlock,
    resolved_so_hieu: Optional[str] = None,
) -> Dict[str, Any]:
    """Giá trị cần có trên `chunk.metadata` để coi là đã cover block."""
    req: Dict[str, Any] = {}
    
    # Tương tự, dùng tiền tố cho coverage check
    if block.dieu:
        req["dieu"] = _normalize_with_prefix(block.dieu, "dieu")
    if block.khoan:
        req["khoan"] = _normalize_with_prefix(block.khoan, "khoan")
    if block.diem:
        req["diem"] = _normalize_with_prefix(block.diem, "diem")
    if block.phan:
        req["phan"] = _normalize_with_prefix(block.phan, "phan")
    if block.chuong:
        req["chuong"] = _normalize_with_prefix(block.chuong, "chuong")
    if block.muc:
        req["muc"] = _normalize_with_prefix(block.muc, "muc")
        
    if block.so_hieu and str(block.so_hieu).strip():
        req["so_hieu"] = str(block.so_hieu).strip()
    elif resolved_so_hieu and str(resolved_so_hieu).strip():
        req["so_hieu"] = str(resolved_so_hieu).strip()
        
    return req


def coverage_field_matches(expected: Any, actual: Any, field: str) -> bool:
    """So khớp metadata chunk với giá trị từ ArticleBlock (hỗ trợ có/không tiền tố)."""
    if actual is None:
        return False
        
    s_expected = str(expected).strip()
    s_actual = str(actual).strip()
    
    if field == "so_hieu":
        return s_actual == s_expected
        
    # Nếu actual là "Điều 1" và expected là "1", hoặc ngược lại, vẫn coi là khớp
    if s_actual == s_expected:
        return True
        
    # Thử bóc tách phần số để so sánh
    def _get_number(s: str) -> str:
        parts = s.split()
        return parts[-1] if len(parts) > 1 else s
        
    return _get_number(s_actual) == _get_number(s_expected)
