"""
Legal Agent Tools — Bộ công cụ tìm kiếm cho LangGraph Agent.

Gồm 3 tool cốt lõi:
1. vector_search         — Tìm kiếm ngữ nghĩa (semantic) trong ChromaDB.
2. chunk_metadata_search — Tìm kiếm chính xác theo Điều/Khoản/Số hiệu trong ChromaDB.
3. doc_metadata_search   — Tra cứu thông tin văn bản trong SQLite.

Mỗi tool trả về ToolOutput (xem schemas.py).
Chunks dùng ChromaQueryResult trực tiếp (không wrap thêm).
Documents dùng DocumentItem DTO để tách khỏi ORM session.

Helper nội bộ:
- _get_base_chunk_id      — Chuẩn hóa chunk_id, loại bỏ hậu tố __dup_N.
- _filter_redundant_chunks — Loại bỏ các chunk con khi tổ tiên đã có trong kết quả.

Method trong LegalAgentTools:
- _evaluate_refs — Đánh giá độ cần thiết của các chunk tham chiếu bằng LLM.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from src.api import RemoteAPIClient
from src.indexing.vector_store import ChromaQueryRequest, ChromaQueryResult, ChromaStore
from src.search.search import SearchService
from system.database.db_respository import DocumentMetadataRepository, DocumentRelationRepository
from system.database.db import DocumentMetadataDB, DocumentRelationDB
from src.indexing.parsing.extract_metadata import Extractor
from .schemas import DocumentItem, RefEvaluationResult, RefScore, ToolOutput
from .prompts import EVALUATE_REFS_PROMPT

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


def _get_base_chunk_id(chunk_id: str) -> str:
    """Chuẩn hóa chunk_id bằng cách loại bỏ hậu tố __dup_N ở từng segment.

    Ví dụ:
        "91_2015_qh13.dieu_6__dup_0.khoan_1" -> "91_2015_qh13.dieu_6.khoan_1"
    """
    segments = chunk_id.strip().split(".")
    clean_segments = [
        seg.rsplit("__dup_", 1)[0] if "__dup_" in seg else seg
        for seg in segments
    ]
    return ".".join(clean_segments)


def _filter_redundant_chunks(
    chunks: List[ChromaQueryResult],
) -> List[ChromaQueryResult]:
    """Loại bỏ các chunk con (cháu, chắt) nếu tổ tiên của chúng đã xuất hiện
    trong cùng danh sách kết quả.

    Nguyên tắc: chunk_id được tổ chức theo cấu trúc phân cấp dấu-chấm::

        <so_hieu>.<section_a>.<section_b>.<section_c>...

    Chunk B là con của Chunk A khi base_id của A là tiền tố của base_id của B.
    Nếu cả A và B cùng có mặt, B bị loại bỏ vì thông tin B đã nằm trong A.

    Args:
        chunks: Danh sách kết quả truy vấn từ ChromaDB, thứ tự được giữ nguyên.

    Returns:
        Danh sách chunks đã lọc, không chứa chunk nào có tổ tiên trong danh sách.
    """
    if not chunks:
        return []

    # Tập hợp tất cả base_id đang có trong kết quả để tra cứu O(1)
    retrieved_base_ids: set[str] = {
        _get_base_chunk_id(c.chunk_id) for c in chunks
    }

    filtered: List[ChromaQueryResult] = []
    for chunk in chunks:
        base_id = _get_base_chunk_id(chunk.chunk_id)
        segments = base_id.split(".")

        # Sinh tất cả tổ tiên (từ gần nhất đến xa nhất): bỏ lần lượt segment cuối
        ancestors = {
            ".".join(segments[:depth])
            for depth in range(1, len(segments))
        }

        if ancestors & retrieved_base_ids:
            # Có ít nhất một tổ tiên đã được lấy → bỏ chunk này
            logger.debug(
                "[filter_redundant] Bỏ chunk con '%s' (tổ tiên đã có trong kết quả).",
                chunk.chunk_id,
            )
        else:
            filtered.append(chunk)

    return filtered


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
        relation_repo: Optional[DocumentRelationRepository] = None,
        meta_repo: Optional[DocumentMetadataRepository] = None,
        api_client: Optional[RemoteAPIClient] = None,
    ) -> None:
        self.search_service = search_service
        self.chroma_store = chroma_store
        self.relation_repo = relation_repo
        self.meta_repo = meta_repo
        self.api_client = api_client  # Dùng để gọi LLM trong _evaluate_refs

    def vector_search(
        self,
        query: str,
        top_k_retrieve: int = 50,
        top_k_rerank: Optional[int] = 5,
        use_rerank: bool = True,
        trang_thai: Optional[int] = 1
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
            metadata_filter = {"section_type": ['dieu', 'khoan', 'diem']}
            if trang_thai is not None:
                metadata_filter["trang_thai"] = trang_thai
                
            # 1. Lấy kết quả từ ChromaDB (Retrieve)
            candidates: List[ChromaQueryResult] = self.search_service._retrieve(
                query=query,
                top_k=top_k_retrieve,
                metadata_filter=metadata_filter,
            )

            if not candidates:
                return ToolOutput(
                    tool_name=tool_name,
                    success=False,
                    display_text="Không tìm thấy thông tin liên quan.",
                )

            # 2. Filter redundant (Lọc trùng cha/con) TRƯỚC KHI rerank
            filtered_chunks = _filter_redundant_chunks(candidates)

            # 3. Rerank (Chấm điểm và sắp xếp lại bằng mô hình Cross-Encoder)
            if use_rerank and self.search_service.reranker:
                chunks = self.search_service.reranker.rerank(
                    query=query,
                    documents=filtered_chunks,
                    top_k=top_k_rerank or len(filtered_chunks)
                )
            else:
                chunks = filtered_chunks[:top_k_rerank] if top_k_rerank else filtered_chunks

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
        trang_thai: Optional[int] = 1,
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

            if trang_thai is not None:
                conditions.append({"trang_thai": {"$eq": trang_thai}})

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

            chunks = _filter_redundant_chunks(chunks)

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
                # Tăng limit lên rất cao để vét cạn DB, vì mệnh đề LIKE %tên% sẽ trả về rất nhiều 
                # văn bản liên quan (luật sửa đổi, nghị định hướng dẫn, v.v.)
                candidates = self.meta_repo.search_by_name(ten_van_ban.strip(), limit=limit * 20)
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

    def doc_relation_search(
        self,
        so_hieu: str
    ) -> ToolOutput:
        """
        Tra cứu quan hệ của một văn bản (bị thay thế, sửa đổi, hiệu lực).
        """
        tool_name = "doc_relation_search"

        if not self.meta_repo:
            return ToolOutput(
                tool_name=tool_name,
                success=False,
                display_text="Database SQLite chưa được khởi tạo.",
            )

        try:
            # 1. Lấy thông tin metadata cơ bản (để biết còn hiệu lực không)
            doc_row = self.meta_repo.get_by_so_hieu(so_hieu)
            if not doc_row:
                return ToolOutput(
                    tool_name=tool_name,
                    success=False,
                    display_text=f"Không tìm thấy văn bản nào có số hiệu '{so_hieu}' trong hệ thống.",
                )
            
            doc_item = DocumentItem.from_orm_row(doc_row)
            
            # 2. Tìm các mối quan hệ thông qua Repository
            relations_start, relations_end = self.relation_repo.get_relations_by_entity(so_hieu)
            
            # 3. Xây dựng nội dung Context
            lines = [
                f"Thông tin về văn bản '{doc_item.ten_van_ban or so_hieu}':",
                doc_item.to_display(),
                "\n--- CÁC MỐI QUAN HỆ ---"
            ]
            
            if not relations_start and not relations_end:
                lines.append("Không tìm thấy mối quan hệ sửa đổi/thay thế nào trong hệ thống.")
            else:
                for rel in relations_start:
                    lines.append(f"- Văn bản này {rel.relation_type} văn bản {rel.entity_end}")
                for rel in relations_end:
                    lines.append(f"- Văn bản này bị/được {rel.relation_type} bởi văn bản {rel.entity_start}")
                    
            return ToolOutput(
                tool_name=tool_name,
                success=True,
                documents=[doc_item], # đính kèm doc_item để lỡ node sau cần dùng
                display_text="\n".join(lines)
            )

        except Exception as e:
            logger.exception("[doc_relation_search] Lỗi: %s", e)
            return ToolOutput(
                tool_name=tool_name,
                success=False,
                error=str(e),
                display_text=f"Lỗi khi tra cứu quan hệ văn bản: {e}",
            )

    #Hàm đánh giá xem việc lấy thồn tin từ viện dẫn của 1 chunk có cần thiết hay không
    #Đang làm là lấy query + chunk chính + tất cả chunk tham chiếu để đánh giá (LLM as a judge)
    #Vấn đề: nếu chunk chính đã đầy đủ thông tin thì không cần lấy tham chiếu nữa
    def _evaluate_refs(
        self,
        query: str,
        nvidia_client:Any,
        main_chunk: ChromaQueryResult,
        score_threshold: float = 6.0,
        max_refs: int = 3,
    ) -> List[ChromaQueryResult]:
        """Đánh giá và lọc các chunk tham chiếu (references) của một chunk chính.

        Đây là một LLM-as-a-judge: LLM đọc (Query + Chunk chính + Tất cả chunks tham chiếu)
        và chấm điểm mOc độ cần thiết của từng tham chiếu dưới dạng điểm số 0–10.
        Chỉ giữ lại các tham chiếu có điểm ≥ score_threshold.

        Quy trình 3 bước:
          1. Pre-filter (code logic): loại bỏ ref có quan hệ họ hàng với chunk chính (tổ tiên/con cháu).
          2. Batch fetch (ChromaDB): loại bỏ ref_id không tồn tại trong DB (lỗi parse).
          3. LLM grading: gọi LLM 1 lần duy nhất với toàn bộ ref còn lại.

        Args:
            query: Câu hỏi gốc của người dùng.
            main_chunk: Chunk chính cần đánh giá tham chiếu.
            score_threshold: Ngưỡng điểm tối thiểu để giữ lại một tham chiếu (0–10).
            max_refs: Số lượng tham chiếu tối đa giữ lại sau khi đánh giá.

        Returns:
            Danh sách các ChromaQueryResult tham chiếu được chấp nhận, sắp xếp theo điểm giảm dần.
            Trả về danh sách rỗng nếu không có api_client hoặc không có tham chiếu hợp lệ.
        """
        if self.api_client is None:
            logger.debug("[_evaluate_refs] Không có api_client, bỏ qua bước đánh giá tham chiếu.")
            return []

        # Lấy danh sách ref_id từ metadata
        raw_refs: List[str] = []
        ref_field = main_chunk.metadata.get("reference")
        if ref_field:
            try:
                parsed = json.loads(ref_field)
                if isinstance(parsed, list):
                    raw_refs = [str(r).strip() for r in parsed if r]
            except (json.JSONDecodeError, TypeError):
                logger.warning("[_evaluate_refs] Không parse được trường 'reference' của chunk '%s'.", main_chunk.chunk_id)

        if not raw_refs:
            return []

        # Bước 1: Pre-filter — Loại bỏ ref có quan hệ họ hàng (tổ tiên/con cháu)
        # Logic: nếu main_id là tiền tố của ref_id (ref là con cháu),
        #        hoặc ref_id là tiền tố của main_id (ref là tổ tiên),
        #        thì thông tin đã bao hàm trong nhau → không cần đánh giá.
        # ---
        main_base_id = _get_base_chunk_id(main_chunk.chunk_id)
        candidate_ref_ids: List[str] = []
        for ref_id in raw_refs:
            ref_base_id = _get_base_chunk_id(ref_id)
            is_ancestor = main_base_id.startswith(ref_base_id + ".")
            is_descendant = ref_base_id.startswith(main_base_id + ".")
            if is_ancestor or is_descendant:
                logger.debug(
                    "[_evaluate_refs] Bỏ qua ref họ hàng '%s' (ỡng/con/cháu) với chunk '%s'.",
                    ref_id, main_chunk.chunk_id,
                )
                continue
            candidate_ref_ids.append(ref_id)

        if not candidate_ref_ids:
            return []

        # Bước 2: Batch fetch — Loại bỏ ref_id không tồn tại trong ChromaDB (lỗi parse)
        fetched_chunks: List[ChromaQueryResult] = self.chroma_store.get_by_ids(candidate_ref_ids)
        ref_by_id: Dict[str, ChromaQueryResult] = {c.chunk_id: c for c in fetched_chunks}

        valid_ref_chunks: List[ChromaQueryResult] = []
        for ref_id in candidate_ref_ids:
            chunk = ref_by_id.get(ref_id)
            if chunk is None:
                logger.debug("[_evaluate_refs] ref_id '%s' không tồn tại trong DB (lỗi parse).", ref_id)
            else:
                valid_ref_chunks.append(chunk)

        if not valid_ref_chunks:
            return []

        # Bước 3: LLM Grading — Gọi LLM 1 lần duy nhất để chấm điểm toàn bộ tham chiếu
        refs_block = "\n".join(
            f'[{chunk.chunk_id}]\n{chunk.metadata.get("full_text") or chunk.text}'
            for chunk in valid_ref_chunks
        )
        prompt = (
            EVALUATE_REFS_PROMPT
            + f"\n\nCâu hỏi của người dùng:\n{query}\n\n"
            + f"Nội dung chính:\n{main_chunk.metadata.get('full_text') or main_chunk.text}\n\n"
            + f"Các nội dung tham chiếu cần đánh giá:\n{refs_block}"
        )

        valid_chunk_ids = [c.chunk_id for c in valid_ref_chunks]
        try:
            # raw_response = self.api_client.generate(
            #     prompt=prompt,
            #     max_length=512,
            #     temperature=0.0,
            # )
            raw_response = nvidia_client.generate(prompt=prompt)
            eval_result = RefEvaluationResult.from_llm_response(raw_response, valid_chunk_ids)
            scores_by_id: Dict[str, RefScore] = {e.chunk_id: e for e in eval_result.evaluations}
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("[_evaluate_refs] LLM trả về kết quả không hợp lệ: %s", e)
            return []

        # Lọc và sắp xếp theo điểm giảm dần
        scored_refs: List[tuple[float, ChromaQueryResult]] = []
        for chunk in valid_ref_chunks:
            ref_score = scores_by_id.get(chunk.chunk_id)
            if ref_score is None:
                logger.debug("[_evaluate_refs] LLM không trả về điểm cho ref '%s', bỏ qua.", chunk.chunk_id)
                continue

            logger.debug(
                "[_evaluate_refs] ref '%s' | score=%.1f | reasoning='%s'",
                chunk.chunk_id, ref_score.score, ref_score.reasoning,
            )
            if ref_score.score >= score_threshold:
                scored_refs.append((ref_score.score, chunk))

        scored_refs.sort(key=lambda x: x[0], reverse=True)
        top_refs = [chunk for _, chunk in scored_refs[:max_refs]]

        logger.info(
            "[_evaluate_refs] Chunk '%s': %d/%d tham chiếu đạt ngưỡng %.1f (giữ tối đa %d).",
            main_chunk.chunk_id, len(top_refs), len(valid_ref_chunks), score_threshold, max_refs,
        )
        return top_refs


