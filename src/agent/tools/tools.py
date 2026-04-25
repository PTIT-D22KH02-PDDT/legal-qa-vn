"""
LangChain Tools cho Legal QA Agent.

Toàn bộ tool đều trả về `ToolOutput` (xem `schemas.py`) gồm:
- `items`: list các item (chunk/metadata/relation) với metadata đầy đủ.
  Một "main item" từ `search_legal_documents` có thể kèm field `references`
  là list các chunk mà nó tham chiếu tới (nested structure).
- `display_text`: bản text đã format, để đưa trực tiếp vào prompt LLM.

Cách này thay thế cho kiểu cũ (trả string thuần) — vốn làm mất metadata,
khiến `_extract_sources` không hoạt động.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool
from sqlalchemy.orm import Session

from src.indexing.embedding import OnnxEmbeddingModel
from src.indexing.vector_store import ChromaQueryRequest, ChromaStore
from src.search.pipeline import SearchPipeline
from src.system.database.db_respository import (
    DocumentMetadataRepository,
    DocumentRelationRepository,
)

from ..schemas import ArticleBlock, ToolOutput

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _format_chunk_title(meta: dict) -> str:
    parts = []
    if meta.get("dieu"):
        parts.append(f"Điều {meta['dieu']}")
    if meta.get("khoan"):
        parts.append(f"Khoản {meta['khoan']}")
    if meta.get("diem"):
        parts.append(f"Điểm {meta['diem']}")
    title = " ".join(parts) if parts else "Điều khoản"
    # 1A migration: chuẩn key mới là `so_hieu`, fallback đọc `van_ban`
    # để không vỡ với dữ liệu Chroma cũ trước khi re-index.
    so_hieu = meta.get("so_hieu") or meta.get("van_ban")
    if so_hieu:
        title = f"{title} — {so_hieu}"
    return title


def _chunk_to_item(chunk, score=None) -> dict:
    """Convert ChromaQueryResult → dict structured chunk."""
    meta = chunk.metadata or {}
    # 1A migration: chuẩn key mới là `so_hieu`, fallback đọc `van_ban`
    # để tương thích dữ liệu Chroma cũ.
    so_hieu = meta.get("so_hieu") or meta.get("van_ban")
    return {
        "kind": "chunk",
        "chunk_id": getattr(chunk, "chunk_id", None),
        "text": chunk.text,
        "metadata": meta,
        "so_hieu": so_hieu,
        "dieu": meta.get("dieu"),
        "khoan": meta.get("khoan"),
        "diem": meta.get("diem"),
        "chuong": meta.get("chuong"),
        "score": score,
        "title": _format_chunk_title(meta),
    }


def _metadata_row_to_item(row, score: Optional[float] = None) -> dict:
    """Convert `DocumentMetadataDB` → dict item chuẩn cho ToolOutput."""
    return {
        "kind": "metadata",
        "so_hieu": row.so_hieu,
        "ten_van_ban": row.ten_van_ban,
        "loai": row.loai,
        "co_quan_ban_hanh": row.co_quan_ban_hanh,
        "ngay_ban_hanh": row.ngay_ban_hanh,
        "ngay_co_hieu_luc": row.ngay_co_hieu_luc,
        "so_dieu": row.so_dieu,
        "score": score,
        "title": f"{row.ten_van_ban or ''} ({row.so_hieu})".strip(),
    }


def _parse_reference_ids(meta: Optional[dict]) -> List[str]:
    """
    Parse `metadata.reference` thành List[str].
    - Nếu đã là list → dùng trực tiếp.
    - Nếu là string (JSON hoặc comma-separated) → parse.
    - Nếu None/thiếu → [].
    """
    if not meta:
        return []
    raw = meta.get("reference")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(r).strip() for r in raw if str(r).strip()]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        # thử JSON trước
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(r).strip() for r in parsed if str(r).strip()]
        except json.JSONDecodeError:
            pass
        # fallback: comma-separated
        return [p.strip() for p in s.split(",") if p.strip()]
    return []


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_vn(s: str) -> str:
    """Lowercase + remove diacritics + collapse spaces. Dùng cho fuzzy match."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    stripped = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return _WHITESPACE_RE.sub(" ", stripped.lower().strip())


def _fuzzy_score(a: str, b: str) -> float:
    """Ratio giữa 2 string sau khi normalize (0-1). 0 nếu có chuỗi rỗng."""
    na, nb = _normalize_vn(a), _normalize_vn(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _is_ancestor_ref(main_chunk_id: Optional[str], ref_id: str) -> bool:
    """True nếu `ref_id` là ancestor (văn bản/chương/điều cha) của main chunk.

    Heuristic dựa prefix: chunk_id được tạo phân cấp theo section_id
    (vd main = "102/2017/dieu_5/khoan_2", ref = "102/2017" → ancestor).
    Lọc kiểu ref này vì câu "theo Bộ luật này" sẽ tạo ref trỏ về văn bản cha
    — không có giá trị bổ sung ngữ cảnh cho câu trả lời.
    """
    if not main_chunk_id or not ref_id:
        return False
    return main_chunk_id.startswith(ref_id) and main_chunk_id != ref_id


# ----------------------------------------------------------------------
# Tools class
# ----------------------------------------------------------------------
class LegalDocumentTools:
    """Tập hợp các tools cho Legal Document Agent."""

    # Giá trị mặc định khi include_references=True: chỉ lấy refs của top-N
    DEFAULT_MAX_MAIN_WITH_REFS = 2

    def __init__(
        self,
        chroma_store: ChromaStore,
        embedding_model: OnnxEmbeddingModel,
        db_session: Optional[Session] = None,
        retrieval_service: Optional[SearchPipeline] = None,
    ):
        self.chroma_store = chroma_store
        self.db_session = db_session
        self.retrieval_service = retrieval_service or SearchPipeline(
            chroma_store, embedding_model
        )
        self.meta_repo = (
            DocumentMetadataRepository(db_session) if db_session else None
        )
        self.rel_repo = (
            DocumentRelationRepository(db_session) if db_session else None
        )

    # ------------------------------------------------------------------
    # Internal helper: fetch reference chunks for a given main chunk
    # ------------------------------------------------------------------
    def _fetch_reference_items(
        self,
        main_item: dict,
        exclude_ids: Optional[set] = None,
    ) -> List[dict]:
        """Trả về list item references của 1 main chunk (đã dedupe với exclude_ids)."""
        meta = main_item.get("metadata") or {}
        ref_ids = _parse_reference_ids(meta)
        if not ref_ids:
            return []
        # Loại bỏ self-ref, exclude_ids, và ancestor refs
        # (ref trỏ về văn bản/chương cha, vd "theo Bộ luật này").
        main_id = main_item.get("chunk_id")
        exclude = set(exclude_ids or ())
        if main_id:
            exclude.add(main_id)
        to_fetch = [
            rid for rid in ref_ids
            if rid
            and rid not in exclude
            and not _is_ancestor_ref(main_id, rid)
        ]
        if not to_fetch:
            return []
        try:
            ref_chunks = self.chroma_store.get_by_ids(to_fetch)
        except Exception as e:
            logger.warning("[_fetch_reference_items] get_by_ids failed: %s", e)
            return []
        return [_chunk_to_item(c) for c in ref_chunks]

    # ------------------------------------------------------------------
    # 1) search_legal_documents  (Vector search + optional refs)
    # ------------------------------------------------------------------
    def search_legal_documents(
        self,
        query: str,
        top_k: int = 5,
        filter_by_type: Optional[List[str]] = None,
        include_references: bool = False,
        max_main_with_refs: Optional[int] = None,
    ) -> ToolOutput:
        """Tìm kiếm các điều luật, khoản liên quan dựa trên câu hỏi (Vector Search).

        Args:
            query: câu hỏi tự nhiên.
            top_k: số chunk kết quả chính.
            filter_by_type: lọc theo loại chunk (mặc định dieu/khoan/diem).
            include_references: nếu True, attach thêm các chunk mà mỗi main chunk
                tham chiếu (đọc từ `metadata.reference`). Mỗi main item sẽ có
                thêm field `references: List[dict]`. Chỉ áp dụng cho top-N main.
            max_main_with_refs: số main chunk đầu được attach references
                (mặc định `DEFAULT_MAX_MAIN_WITH_REFS`).
        """
        tool_name = "search_legal_documents"
        try:
            results = self.retrieval_service.search(
                query=query,
                top_k=top_k,
                filter_by_type=filter_by_type or ["dieu", "khoan", "diem"],
            )
            if not results:
                return ToolOutput(
                    tool_name=tool_name, success=False, items=[],
                    display_text="Không tìm thấy tài liệu liên quan.",
                )

            items: List[dict] = []
            for r in results:
                score = r.score_rerank if r.score_rerank is not None else r.distance
                items.append(_chunk_to_item(r, score=score))

            # Attach references cho top-N main chunk
            if include_references:
                limit = (
                    max_main_with_refs
                    if max_main_with_refs is not None
                    else self.DEFAULT_MAX_MAIN_WITH_REFS
                )
                limit = max(0, min(limit, len(items)))
                main_ids = {it.get("chunk_id") for it in items if it.get("chunk_id")}
                for it in items[:limit]:
                    refs = self._fetch_reference_items(it, exclude_ids=main_ids)
                    if refs:
                        it["references"] = refs

            # Build display_text (indent references dưới mỗi main)
            display_lines: List[str] = []
            for i, it in enumerate(items, 1):
                score = it.get("score")
                score_text = f"{score:.4f}" if isinstance(score, (int, float)) else "N/A"
                display_lines.append(
                    f"{i}. {it['title']}\n"
                    f"   Nội dung: {(it.get('text') or '')[:300]}...\n"
                    f"   Độ liên quan: {score_text}"
                )
                for j, ref in enumerate(it.get("references") or [], 1):
                    display_lines.append(
                        f"   └─ Ref {j}. {ref.get('title')}\n"
                        f"        {(ref.get('text') or '')[:200]}..."
                    )

            return ToolOutput(
                tool_name=tool_name, success=True, items=items,
                display_text="\n".join(display_lines),
            )
        except Exception as e:
            logger.exception("[%s] error", tool_name)
            return ToolOutput(
                tool_name=tool_name, success=False, error=str(e),
                display_text=f"Lỗi tìm kiếm: {e}",
            )

    # ------------------------------------------------------------------
    # 2) search_document_metadata  (flexible params)
    # ------------------------------------------------------------------
    def search_document_metadata(
        self,
        so_hieu: Optional[str] = None,
        ten_van_ban: Optional[str] = None,
        doc_type: Optional[str] = None,
        org_unit: Optional[str] = None,
        limit: int = 10,
    ) -> ToolOutput:
        """Tìm tài liệu theo số hiệu / tên văn bản / loại / cơ quan ban hành.

        Thứ tự ưu tiên:
        1. `so_hieu` (exact match, deterministic).
        2. `ten_van_ban` (LIKE + fuzzy rerank bằng SequenceMatcher).
        3. `doc_type` / `org_unit` dùng để LỌC THÊM trên kết quả phía trên,
           hoặc đóng vai trò truy vấn chính nếu không có so_hieu/ten_van_ban.
        """
        tool_name = "search_document_metadata"
        if not self.meta_repo:
            return ToolOutput(
                tool_name=tool_name, success=False,
                error="no db session",
                display_text="Lỗi: Database session chưa khởi tạo.",
            )

        # Chuẩn hóa input
        so_hieu = (so_hieu or "").strip() or None
        ten_van_ban = (ten_van_ban or "").strip() or None
        doc_type = (doc_type or "").strip() or None
        org_unit = (org_unit or "").strip() or None

        try:
            rows: List[Any] = []
            used_filter: str = "all"

            # 1) Exact so_hieu
            if so_hieu:
                row = self.meta_repo.get_by_so_hieu(so_hieu)
                if row:
                    rows = [row]
                    used_filter = f"so_hieu={so_hieu}"

            # 2) ten_van_ban (fuzzy)
            if not rows and ten_van_ban:
                rows = self.meta_repo.search_by_name(ten_van_ban, limit=max(limit * 3, 30))
                used_filter = f"ten_van_ban~{ten_van_ban}"

            # 3) doc_type (hoặc dùng làm main query nếu chưa có)
            if not rows and doc_type:
                rows = self.meta_repo.get_by_loai(doc_type)
                used_filter = f"loai={doc_type}"

            # 4) Fallback: lấy danh sách
            if not rows and not (so_hieu or ten_van_ban or doc_type or org_unit):
                rows = self.meta_repo.get_all(limit=limit)
                used_filter = "all"

            # Lọc thêm theo doc_type (nếu đã có rows trước đó)
            if rows and doc_type and used_filter != f"loai={doc_type}":
                rows = [r for r in rows if (r.loai or "").strip() == doc_type]

            # Lọc thêm theo org_unit
            if rows and org_unit:
                ou = org_unit.lower()
                rows = [
                    r for r in rows
                    if r.co_quan_ban_hanh and ou in r.co_quan_ban_hanh.lower()
                ]

            if not rows:
                return ToolOutput(
                    tool_name=tool_name, success=False, items=[],
                    display_text="Không tìm thấy tài liệu nào phù hợp.",
                )

            # Fuzzy rerank khi search theo tên
            if ten_van_ban:
                scored: List[tuple] = []
                for r in rows:
                    s_name = _fuzzy_score(ten_van_ban, r.ten_van_ban or "")
                    s_so = _fuzzy_score(ten_van_ban, r.so_hieu or "")
                    scored.append((max(s_name, s_so), r))
                scored.sort(key=lambda x: x[0], reverse=True)
                rows_with_score = scored[:limit]
                items = [
                    _metadata_row_to_item(r, score=score)
                    for score, r in rows_with_score
                ]
            else:
                items = [_metadata_row_to_item(r) for r in rows[:limit]]

            display = [f"Tìm thấy {len(items)} tài liệu ({used_filter}):"] + [
                (
                    f"{i}. {it.get('ten_van_ban')} ({it.get('so_hieu')}) - {it.get('loai')}"
                    + (f" — score={it['score']:.2f}" if it.get("score") is not None else "")
                )
                for i, it in enumerate(items, 1)
            ]
            return ToolOutput(
                tool_name=tool_name, success=True, items=items,
                display_text="\n".join(display),
            )
        except Exception as e:
            logger.exception("[%s] error", tool_name)
            return ToolOutput(
                tool_name=tool_name, success=False, error=str(e),
                display_text=f"Lỗi: {e}",
            )

    # ------------------------------------------------------------------
    # Helper: resolve `so_hieu` from ArticleBlock (dùng cho điểm 3)
    # ------------------------------------------------------------------
    def _resolve_so_hieu(
        self,
        article_block: ArticleBlock,
        min_score: float = 0.6,
    ) -> Optional[str]:
        """Nếu block không có `so_hieu` nhưng có `document_name`, tìm trong
        `document_metadata` văn bản có tên khớp nhất rồi trả về số hiệu.
        """
        if article_block.so_hieu:
            return article_block.so_hieu.strip() or None
        name = (article_block.document_name or "").strip()
        if not name or not self.meta_repo:
            return None
        try:
            candidates = self.meta_repo.search_by_name(name, limit=20)
        except Exception as e:
            logger.warning("[_resolve_so_hieu] search_by_name failed: %s", e)
            return None
        if not candidates:
            return None
        scored = [
            (max(_fuzzy_score(name, c.ten_van_ban or ""),
                 _fuzzy_score(name, c.so_hieu or "")), c)
            for c in candidates
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]
        if best_score < min_score:
            logger.info(
                "[_resolve_so_hieu] best=%s score=%.2f < %.2f → skip",
                best.so_hieu, best_score, min_score,
            )
            return None
        logger.info(
            "[_resolve_so_hieu] '%s' → %s (score=%.2f)",
            name, best.so_hieu, best_score,
        )
        return best.so_hieu

    # ------------------------------------------------------------------
    # 3) get_specific_article  (với auto-resolve document_name → so_hieu)
    # ------------------------------------------------------------------
    def get_specific_article(self, article_block: ArticleBlock) -> ToolOutput:
        """Lấy nội dung chi tiết của một điều/khoản cụ thể.

        Hỗ trợ 2 nguồn nhận diện văn bản:
        - `article_block.so_hieu`: dùng trực tiếp (ưu tiên, deterministic).
        - `article_block.document_name`: fallback — tìm metadata có tên
          khớp nhất (fuzzy) để lấy `so_hieu`, rồi mới filter Chroma.
        """
        tool_name = "get_specific_article"
        try:
            so_hieu = self._resolve_so_hieu(article_block)

            filter_data = {
                "dieu": article_block.dieu,
                "khoan": article_block.khoan,
                "diem": article_block.diem,
                "so_hieu": so_hieu,
            }
            where_filter = {k: v for k, v in filter_data.items() if v}
            if not where_filter:
                return ToolOutput(
                    tool_name=tool_name, success=False,
                    display_text=(
                        "Không đủ thông tin để tìm kiếm "
                        "(cần ít nhất dieu/khoan/diem hoặc so_hieu)."
                    ),
                )

            # TODO: thay hack query_vector=[0]*768 bằng ChromaStore.get(where=...)
            results = self.chroma_store.query(ChromaQueryRequest(
                query_vector=[0.0] * 768, top_k=1, filter=where_filter,
            ))
            # Backward-compat: dữ liệu Chroma cũ có thể vẫn lưu key `van_ban`.
            if not results and so_hieu:
                legacy_filter = {
                    k: v for k, v in where_filter.items()
                    if k != "so_hieu"
                }
                legacy_filter["van_ban"] = so_hieu
                results = self.chroma_store.query(ChromaQueryRequest(
                    query_vector=[0.0] * 768, top_k=1, filter=legacy_filter,
                ))
            if not results:
                missing = (
                    " (không resolve được số hiệu từ document_name)"
                    if article_block.document_name and not so_hieu
                    else ""
                )
                return ToolOutput(
                    tool_name=tool_name, success=False, items=[],
                    display_text=f"Không tìm thấy điều khoản.{missing}",
                )

            item = _chunk_to_item(results[0])
            display = (
                f"**{item['title']}**\n\n{item['text']}\n\n"
                f"Nguồn: {item.get('so_hieu') or 'N/A'}"
            )
            return ToolOutput(
                tool_name=tool_name, success=True, items=[item],
                display_text=display,
            )
        except Exception as e:
            logger.exception("[%s] error", tool_name)
            return ToolOutput(
                tool_name=tool_name, success=False, error=str(e),
                display_text=f"Lỗi: {e}",
            )

    # ------------------------------------------------------------------
    # 4) find_related_documents (giữ nguyên logic — thao tác relation DB)
    # ------------------------------------------------------------------
    def find_related_documents(
        self, doc_id: str, relation_type: Optional[str] = None,
    ) -> ToolOutput:
        """Tìm các văn bản liên quan (sửa đổi, bổ sung, thay thế, v.v.)."""
        tool_name = "find_related_documents"
        if not self.rel_repo or not self.meta_repo:
            return ToolOutput(
                tool_name=tool_name, success=False,
                error="no db session",
                display_text="Lỗi: Database session chưa khởi tạo.",
            )
        try:
            related = self.rel_repo.get_related_documents(doc_id)
            all_rels = (
                (related.get("related_from") or [])
                + (related.get("related_to") or [])
            )
            if relation_type:
                all_rels = [
                    r for r in all_rels
                    if r.relation_type and r.relation_type.value == relation_type
                ]
            if not all_rels:
                return ToolOutput(
                    tool_name=tool_name, success=False, items=[],
                    display_text="Không tìm thấy văn bản liên quan.",
                )

            items = []
            display_lines = [f"Tìm thấy {len(all_rels)} tài liệu liên quan:"]
            for i, rel in enumerate(all_rels, 1):
                target_id = (
                    rel.entity_end if rel.entity_start == doc_id else rel.entity_start
                )
                target_doc = self.meta_repo.get_by_so_hieu(target_id)
                rel_name = rel.relation_type.value if rel.relation_type else "N/A"
                if target_doc:
                    items.append({
                        "kind": "relation",
                        "so_hieu": target_doc.so_hieu,
                        "ten_van_ban": target_doc.ten_van_ban,
                        "relation_type": rel_name,
                        "title": f"{target_doc.ten_van_ban} ({target_doc.so_hieu})",
                    })
                    display_lines.append(
                        f"{i}. {target_doc.so_hieu}: {target_doc.ten_van_ban} "
                        f"(Quan hệ: {rel_name})"
                    )
            return ToolOutput(
                tool_name=tool_name, success=bool(items), items=items,
                display_text="\n".join(display_lines),
            )
        except Exception as e:
            logger.exception("[%s] error", tool_name)
            return ToolOutput(
                tool_name=tool_name, success=False, error=str(e),
                display_text=f"Lỗi: {e}",
            )

    # ------------------------------------------------------------------
    # 5) find_cross_references (REWRITTEN — dựa metadata.reference)
    # ------------------------------------------------------------------
    def find_cross_references(
        self,
        article_block: Optional[ArticleBlock] = None,
        chunk_id: Optional[str] = None,
    ) -> ToolOutput:
        """Lấy các chunk được tham chiếu bởi một chunk gốc.

        Ý nghĩa: chunk gốc (main) có field `metadata.reference` là danh sách
        `chunk_id` mà nó trỏ tới. Tool này chỉ cần đọc list đó rồi dùng
        `ChromaStore.get_by_ids` để fetch nội dung các chunk được tham chiếu.

        Args:
            article_block: ArticleBlock để xác định chunk gốc (cần dieu/... +
                so_hieu hoặc document_name).
            chunk_id: nếu đã biết sẵn `chunk_id` của main chunk (vd lấy từ
                output của `search_legal_documents`/`get_specific_article`),
                truyền thẳng vào để bỏ qua bước query metadata.
        """
        tool_name = "find_cross_references"
        try:
            # --- B1: xác định source chunk ---
            source_chunk = None
            if chunk_id:
                hits = self.chroma_store.get_by_ids([chunk_id])
                source_chunk = hits[0] if hits else None
            elif article_block is not None:
                so_hieu = self._resolve_so_hieu(article_block)
                filter_data = {
                    "dieu": article_block.dieu,
                    "khoan": article_block.khoan,
                    "diem": article_block.diem,
                    "so_hieu": so_hieu,
                }
                where_filter = {k: v for k, v in filter_data.items() if v}
                if not where_filter:
                    return ToolOutput(
                        tool_name=tool_name, success=False,
                        display_text="Không đủ thông tin để xác định chunk gốc.",
                    )
                hits = self.chroma_store.query(ChromaQueryRequest(
                    query_vector=[0.0] * 768, top_k=1, filter=where_filter,
                ))
                # Backward-compat: dữ liệu Chroma cũ có thể vẫn lưu key `van_ban`.
                if not hits and so_hieu:
                    legacy_filter = {
                        k: v for k, v in where_filter.items()
                        if k != "so_hieu"
                    }
                    legacy_filter["van_ban"] = so_hieu
                    hits = self.chroma_store.query(ChromaQueryRequest(
                        query_vector=[0.0] * 768, top_k=1, filter=legacy_filter,
                    ))
                source_chunk = hits[0] if hits else None
            else:
                return ToolOutput(
                    tool_name=tool_name, success=False,
                    display_text="Cần truyền `article_block` hoặc `chunk_id`.",
                )

            if source_chunk is None:
                return ToolOutput(
                    tool_name=tool_name, success=False, items=[],
                    display_text="Không tìm thấy chunk gốc.",
                )

            source_item = _chunk_to_item(source_chunk)
            source_id = source_item.get("chunk_id")

            # --- B2: parse reference ids từ metadata ---
            # Loại: self-ref + ancestor refs (ref trỏ về văn bản/chương cha,
            # kiểu "theo Bộ luật này" — không bổ sung ngữ cảnh).
            ref_ids = _parse_reference_ids(source_chunk.metadata)
            ref_ids = [
                rid for rid in ref_ids
                if rid
                and rid != source_id
                and not _is_ancestor_ref(source_id, rid)
            ]
            if not ref_ids:
                return ToolOutput(
                    tool_name=tool_name, success=True, items=[source_item],
                    display_text=(
                        f"Chunk gốc **{source_item['title']}** không tham chiếu "
                        f"tới chunk nào khác."
                    ),
                )

            # --- B3: fetch referenced chunks ---
            ref_chunks = self.chroma_store.get_by_ids(ref_ids)
            if not ref_chunks:
                return ToolOutput(
                    tool_name=tool_name, success=False, items=[source_item],
                    display_text=(
                        f"Tìm thấy {len(ref_ids)} chunk_id tham chiếu nhưng "
                        f"không load được nội dung."
                    ),
                )

            ref_items = [_chunk_to_item(c) for c in ref_chunks]
            source_item["references"] = ref_items

            display = [
                f"Chunk gốc **{source_item['title']}** tham chiếu tới "
                f"{len(ref_items)} chunk:"
            ] + [
                f"   {i}. {ri.get('title')}: {(ri.get('text') or '')[:150]}..."
                for i, ri in enumerate(ref_items, 1)
            ]
            return ToolOutput(
                tool_name=tool_name, success=True, items=[source_item],
                display_text="\n".join(display),
            )
        except Exception as e:
            logger.exception("[%s] error", tool_name)
            return ToolOutput(
                tool_name=tool_name, success=False, error=str(e),
                display_text=f"Lỗi: {e}",
            )

    # ------------------------------------------------------------------
    def get_tools_list(self) -> List[StructuredTool]:
        """Bọc methods thành LangChain StructuredTool."""
        methods = [
            self.search_legal_documents,
            self.search_document_metadata,
            self.get_specific_article,
            self.find_related_documents,
            self.find_cross_references,
        ]
        return [
            StructuredTool.from_function(
                func=method, name=method.__name__, description=method.__doc__,
            )
            for method in methods
        ]
