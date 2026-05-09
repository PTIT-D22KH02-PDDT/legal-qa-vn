"""
Legal Agent Tools — Bộ công cụ tìm kiếm cho LangGraph Agent.

Gồm 3 tool cốt lõi:
1. vector_search       — Tìm kiếm ngữ nghĩa (semantic) trong ChromaDB.
2. metadata_search     — Tìm kiếm chính xác theo Điều/Khoản/Số hiệu trong ChromaDB.
3. doc_metadata_search — Tra cứu thông tin văn bản trong SQLite.

Mỗi tool trả về ToolOutput (xem schemas.py).
Chunks dùng ChromaQueryResult trực tiếp (không wrap thêm).
Documents dùng DocumentItem DTO để tách khỏi ORM session.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from src.indexing.vector_store import ChromaQueryRequest, ChromaQueryResult, ChromaStore
from src.search.search import SearchService
from system.database.db_respository import DocumentMetadataRepository
from system.database.db import DocumentMetadataDB
from src.indexing.parsing.extract_metadata import Extractor
from .schemas import DocumentItem, ToolOutput

logger = logging.getLogger(__name__)


_WHITESPACE_RE = re.compile(r"\s+")

def _normalize_vn(s: str) -> str:
    """Lowercase + bỏ dấu + chuẩn hóa khoảng trắng. Dùng cho fuzzy match."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    stripped = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return _WHITESPACE_RE.sub(" ", stripped.lower().strip())


def _fuzzy_score(a: str, b: str) -> float:
    """Tỷ lệ tương đồng giữa 2 chuỗi (0-1) sau khi normalize."""
    na, nb = _normalize_vn(a), _normalize_vn(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _chunk_display(result: ChromaQueryResult) -> str:
    """Format một ChromaQueryResult thành text đưa vào LLM."""
    meta = result.metadata or {}
    parts = []
    if meta.get("so_hieu"):
        parts.append(f"[{meta['so_hieu']}]")
    if meta.get("dieu") is not None:
        parts.append(f"Điều {meta['dieu']}")
    if meta.get("khoan") is not None:
        parts.append(f"Khoản {meta['khoan']}")
    if meta.get("diem"):
        parts.append(f"Điểm {meta['diem']}")
    header = " ".join(parts) or "Điều khoản"
    return f"**{header}**\n{result.text}"


def _build_chunks_display(chunks: List[ChromaQueryResult]) -> str:
    """Ghép danh sách chunk thành display_text."""
    if not chunks:
        return "Không tìm thấy thông tin liên quan."
    return "\n\n".join(f"{i+1}. {_chunk_display(c)}" for i, c in enumerate(chunks))


def _build_docs_display(docs: List[DocumentItem]) -> str:
    """Ghép danh sách DocumentItem thành display_text."""
    if not docs:
        return "Không tìm thấy văn bản phù hợp."
    return "\n\n".join(f"{i+1}. {d.to_display()}" for i, d in enumerate(docs))


class LegalAgentTools:
    """
    Bộ công cụ tìm kiếm cho Legal Agent.

    Khởi tạo một lần và tái sử dụng trong suốt vòng đời ứng dụng.
    """

    def __init__(
        self,
        search_service: SearchService,
        chroma_store: ChromaStore,
        meta_repo: Optional[DocumentMetadataRepository] = None,
    ) -> None:
        self.search_service = search_service
        self.chroma_store = chroma_store
        self.meta_repo = meta_repo

    def vector_search(
        self,
        query: str,
        top_k_retrieve: int = 50,
        top_k_rerank: Optional[int] = 5,
        use_rerank: bool = False,
    ) -> ToolOutput:
        """
        Tìm kiếm ngữ nghĩa (semantic search) trong ChromaDB.

        Dùng cho nhánh LEGAL_QUERY và GENERAL trong Agent graph.
        Khi linh_vuc được truyền, bộ lọc metadata sẽ thu hẹp phạm vi tìm kiếm
        về đúng lĩnh vực pháp lý.

        Args:
            query: Câu hỏi hoặc từ khóa tìm kiếm.
            top_k: Số lượng kết quả retrieve ban đầu (mặc định: 10).
            top_k_rerank: Số kết quả giữ lại sau rerank (mặc định: 3).
            linh_vuc: Lĩnh vực pháp lý để lọc metadata. Ví dụ: 'dân sự', 'hình sự'.
            use_rerank: Có dùng cross-encoder rerank không (mặc định: False).

        Returns:
            ToolOutput với chunks (ChromaQueryResult) và display_text.
        """
        tool_name = "vector_search"
        try:

            chunks: List[ChromaQueryResult] = self.search_service.search(
                query=query,
                top_k_retrieve=top_k_retrieve,
                top_k_rerank=top_k_rerank,
                use_rerank=use_rerank,
            )

            if not chunks:
                return ToolOutput(
                    tool_name=tool_name,
                    success=False,
                    display_text="Không tìm thấy thông tin liên quan.",
                )

            return ToolOutput(
                tool_name=tool_name,
                success=True,
                chunks=chunks,
                display_text=_build_chunks_display(chunks),
            )

        except Exception as e:
            logger.exception("[vector_search] Lỗi: %s", e)
            return ToolOutput(
                tool_name=tool_name,
                success=False,
                error=str(e),
                display_text=f"Lỗi khi tìm kiếm: {e}",
            )

    def chunk_metadata_search(
        self,
        # --- Định danh văn bản ---
        so_hieu: Optional[str] = None,
        # --- Cấu trúc văn bản (tất cả là int, sẽ được convert sang "Nhãn N") ---
        phan: Optional[int] = None,
        chuong: Optional[int] = None,
        muc: Optional[int] = None,
        dieu: Optional[int] = None,
        khoan: Optional[int] = None,
        # --- Điểm và phụ lục (str, sẽ được convert sang "Nhãn X") ---
        diem: Optional[str] = None,
        phu_luc: Optional[str] = None,
        phu_luc_phan: Optional[str] = None,
        # --- Metadata bổ sung ---
        section_type: Optional[str] = None,
        parent_id: Optional[str] = None,
        # --- Điều khiển kết quả ---
        top_k: int = 1,
    ) -> ToolOutput:
        """
        Tìm kiếm chính xác theo bộ lọc metadata trong ChromaDB (không qua embedding).

        Dùng cho nhánh DOC_RETRIEVE và LEGAL_QUERY khi người dùng hỏi đích danh
        một Điều/Khoản/Điểm hoặc cấu trúc văn bản cụ thể.

        Tất cả tham số đều tùy chọn — chỉ truyền những gì cần lọc.
        Nhiều tham số → filter kết hợp bằng $and.

        Format metadata lưu trong ChromaDB (theo decode_section_id trong utils.py):
            so_hieu      → "91_2015_qh13"      (dấu '_', lowercase)
            phan         → "Phần 1"
            chuong       → "Chương 2"
            muc          → "Mục 3"
            dieu         → "Điều 6"
            khoan        → "Khoản 1"
            diem         → "Điểm a"
            phu_luc      → "Phụ lục 1"
            phu_luc_phan → "Phụ lục - Phần 2"
            section_type → "dieu" | "khoan" | "diem" | ...   (lowercase, no accent)
            parent_id    → chunk_id của node cha

        Returns:
            ToolOutput với chunks (ChromaQueryResult) khớp bộ lọc.
        """
        # Mapping field_name → (label_prefix, value)
        # Dùng để tự động build conditions mà không cần if thủ công cho từng field
        _LABELED_INT_FIELDS = {
            "phan":     ("Phần",           phan),
            "chuong":   ("Chương",         chuong),
            "muc":      ("Mục",            muc),
            "dieu":     ("Điều",           dieu),
            "khoan":    ("Khoản",          khoan),
        }
        _LABELED_STR_FIELDS = {
            "diem":         ("Điểm",            diem),
            "phu_luc":      ("Phụ lục",         phu_luc),
            "phu_luc_phan": ("Phụ lục - Phần",  phu_luc_phan),
        }

        tool_name = "chunk_metadata_search"
        extractor = Extractor()

        try:
            conditions: List[Dict[str, Any]] = []

            # so_hieu: '91/2015/QH14' → '91_2015_qh14'
            if so_hieu:
                normalized_so_hieu = extractor._extract_so_hieu(so_hieu)
                conditions.append({"so_hieu": {"$eq": normalized_so_hieu}})

            # Các field số nguyên: int → "Nhãn N"
            for field, (label, value) in _LABELED_INT_FIELDS.items():
                if value is not None:
                    conditions.append({field: {"$eq": f"{label} {value}"}})

            # Các field chuỗi: "x" → "Nhãn x"
            for field, (label, value) in _LABELED_STR_FIELDS.items():
                if value:
                    conditions.append({field: {"$eq": f"{label} {value.strip()}"}})

            # section_type và parent_id: truyền thẳng, không cần convert
            if section_type:
                conditions.append({"section_type": {"$eq": section_type.strip()}})
            if parent_id:
                conditions.append({"parent_id": {"$eq": parent_id.strip()}})

            if not conditions:
                return ToolOutput(
                    tool_name=tool_name,
                    success=False,
                    display_text="Cần cung cấp ít nhất một tiêu chí tìm kiếm.",
                )

            chroma_where = conditions[0] if len(conditions) == 1 else {"$and": conditions}

            chunks = self.chroma_store.query(
                ChromaQueryRequest(
                    query_vector=[0.0] * 1024,
                    top_k=top_k,
                    metadata_filter=chroma_where,
                )
            )

            if not chunks:
                return ToolOutput(
                    tool_name=tool_name,
                    success=False,
                    display_text="Không tìm thấy điều khoản theo tiêu chí đã cho.",
                )

            return ToolOutput(
                tool_name=tool_name,
                success=True,
                chunks=chunks,
                display_text=_build_chunks_display(chunks),
            )

        except Exception as e:
            logger.exception("[chunk_metadata_search] Lỗi: %s", e)
            return ToolOutput(
                tool_name=tool_name,
                success=False,
                error=str(e),
                display_text=f"Lỗi khi tra cứu điều khoản: {e}",
            )


    def doc_metadata_search(
        self,
        so_hieu: Optional[str] = None,
        ten_van_ban: Optional[str] = None,
        loai: Optional[str] = None,
        linh_vuc: Optional[str] = None,
        limit: int = 10,
        fuzzy_threshold: float = 0.5,
    ) -> ToolOutput:
        """
        Tra cứu thông tin văn bản pháp luật trong SQLite (legal_documents.db).

        Dùng cho nhánh DOC_RELATION, DOC_RETRIEVE và khi cần kiểm tra
        tình trạng hiệu lực, ngày ban hành của văn bản.
        Args:
            so_hieu: Số hiệu văn bản để tra cứu chính xác. Ví dụ: '45/2019/QH14'.
            ten_van_ban: Tên văn bản để tra cứu mờ (fuzzy match).
            loai: Loại văn bản. Ví dụ: 'Luật', 'Nghị định', 'Thông tư'.
            limit: Số kết quả tối đa (mặc định: 10).
            fuzzy_threshold: Ngưỡng điểm tương đồng khi tìm theo tên (mặc định: 0.5).

        Returns:
            ToolOutput với documents (DocumentItem DTO) và display_text.
        """
        tool_name = "doc_metadata_search"

        if not self.meta_repo:
            return ToolOutput(
                tool_name=tool_name,
                success=False,
                display_text="Database SQLite chưa được khởi tạo.",
            )

        try:
            extractor = Extractor()
            rows = []

            if so_hieu:
                normalized_so_hieu = extractor._extract_so_hieu(so_hieu.strip())
                row = self.meta_repo.get_by_so_hieu(normalized_so_hieu)
                if row:
                    rows = [row]

            elif ten_van_ban:
                candidates = self.meta_repo.search_by_name(ten_van_ban.strip(), limit=limit * 3)
                if candidates:
                    scored = [
                        (
                            max(
                                _fuzzy_score(ten_van_ban, r.ten_van_ban or ""),
                                _fuzzy_score(ten_van_ban, r.so_hieu or ""),
                            ),
                            r,
                        )
                        for r in candidates
                    ]
                    scored.sort(key=lambda x: x[0], reverse=True)
                    rows = [r for score, r in scored if score >= fuzzy_threshold][:limit]

            elif loai:
                normalized_loai = extractor._extract_loai(loai.strip())
                rows = self.meta_repo.get_by_loai(normalized_loai)[:limit]

            elif linh_vuc:
                rows = self.meta_repo.search_by_linh_vuc(linh_vuc.strip(), limit=limit)

            if not rows:
                return ToolOutput(
                    tool_name=tool_name,
                    success=False,
                    display_text="Không tìm thấy văn bản phù hợp.",
                )

            # Convert ORM rows → DocumentItem DTO ngay tại đây, trước khi session có thể đóng
            docs = [DocumentItem.from_orm_row(r) for r in rows]

            return ToolOutput(
                tool_name=tool_name,
                success=True,
                documents=docs,
                display_text=_build_docs_display(docs),
            )

        except Exception as e:
            logger.exception("[doc_metadata_search] Lỗi: %s", e)
            return ToolOutput(
                tool_name=tool_name,
                success=False,
                error=str(e),
                display_text=f"Lỗi khi tra cứu văn bản: {e}",
            )
