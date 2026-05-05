"""
LangChain Tools cho Legal Document Agent.

Tất cả tool đều trả về `ToolOutput` (xem schemas.py) gồm:
- `items`: list chunk/metadata với metadata đầy đủ.
- `display_text`: text đã format, đưa trực tiếp vào prompt LLM.
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

from src.indexing.embedding.remote_embedding import RemoteEmbeddingModel
from src.indexing.embedding.utils import SECTION_TYPE_NAMES as _SECTION_LABELS
from src.indexing.vector_store import ChromaQueryRequest, ChromaStore
from src.search.search import SearchService
from system.database.db_respository import DocumentMetadataRepository

from ..schemas import ArticleBlock, ToolOutput
from ..utils.chroma_metadata import chroma_filter_from_article_block

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Helpers (Fuzzy Match & Tiếng Việt)
# ----------------------------------------------------------------------
_WHITESPACE_RE = re.compile(r"\s+")

def _normalize_vn(s: str) -> str:
    """Lowercase + remove diacritics + collapse spaces. Dùng cho fuzzy match."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    stripped = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return _WHITESPACE_RE.sub(" ", stripped.lower().strip())

def _fuzzy_score(a: str, b: str) -> float:
    """Ratio giữa 2 string sau khi normalize (0-1)."""
    na, nb = _normalize_vn(a), _normalize_vn(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()

def _format_chunk_title(meta: dict) -> str:
    def _one(label_key: str, raw) -> str:
        if raw is None or raw == "":
            return ""
        s = str(raw).strip()
        prefix = _SECTION_LABELS.get(label_key, "")
        if prefix and s.startswith(prefix):
            return s
        return f"{prefix} {s}".strip() if prefix else s

    parts = []
    d, k, i = meta.get("dieu"), meta.get("khoan"), meta.get("diem")
    if d is not None and d != "":
        parts.append(_one("dieu", d))
    if k is not None and k != "":
        parts.append(_one("khoan", k))
    if i is not None and i != "":
        parts.append(_one("diem", i))
    title = " ".join(parts) if parts else "Điều khoản"
    so_hieu = meta.get("so_hieu")
    if so_hieu:
        title = f"{title} — {so_hieu}"
    return title

def _chunk_to_item(chunk, score=None) -> dict:
    meta = chunk.metadata or {}
    return {
        "kind": "chunk",
        "chunk_id": getattr(chunk, "chunk_id", None),
        "text": chunk.text,
        "metadata": meta,
        "so_hieu": meta.get("so_hieu"),
        "dieu": meta.get("dieu"),
        "khoan": meta.get("khoan"),
        "diem": meta.get("diem"),
        "chuong": meta.get("chuong"),
        "score": score,
        "title": _format_chunk_title(meta),
    }

def _metadata_row_to_item(row, score: Optional[float] = None) -> dict:
    """Convert `DocumentMetadataDB` -> dict item chuẩn cho ToolOutput."""
    return {
        "kind": "metadata",
        "so_hieu": row.so_hieu,
        "ten_van_ban": row.ten_van_ban,
        "loai": row.loai,
        "co_quan_ban_hanh": row.co_quan_ban_hanh,
        "ngay_ban_hanh": row.ngay_ban_hanh,
        "ngay_co_hieu_luc": row.ngay_co_hieu_luc,
        "score": score,
        "title": f"{row.ten_van_ban or ''} ({row.so_hieu})".strip(),
    }

def _parse_reference_ids(meta: Optional[dict]) -> List[str]:
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
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(r).strip() for r in parsed if str(r).strip()]
        except json.JSONDecodeError:
            pass
        return [p.strip() for p in s.split(",") if p.strip()]
    return []

def _is_ancestor_ref(main_chunk_id: Optional[str], ref_id: str) -> bool:
    if not main_chunk_id or not ref_id:
        return False
    return main_chunk_id.startswith(ref_id) and main_chunk_id != ref_id


# ----------------------------------------------------------------------
# Tools class
# ----------------------------------------------------------------------
class LegalDocumentTools:
    """Tập hợp các tools cho Legal Document Agent."""

    DEFAULT_MAX_MAIN_WITH_REFS = 2

    def __init__(
        self,
        chroma_store: ChromaStore,
        embedding_model: RemoteEmbeddingModel,
        db_session: Optional[Session] = None,
        retrieval_service: Optional[SearchService] = None,
        **kwargs,
    ):
        self.chroma_store = chroma_store
        self.db_session = db_session
        self.retrieval_service = retrieval_service or SearchService(
            chroma_store, embedding_model
        )
        self.meta_repo = DocumentMetadataRepository(db_session) if db_session else None

    # ------------------------------------------------------------------
    # Helper: resolve `so_hieu` from document_name
    # ------------------------------------------------------------------
    def _resolve_so_hieu(self, article_block: ArticleBlock, min_score: float = 0.6) -> Optional[str]:
        if article_block.so_hieu:
            return article_block.so_hieu.strip() or None
        name = (article_block.document_name or "").strip()
        if not name or not self.meta_repo:
            return None
        try:
            candidates = self.meta_repo.search_by_name(name, limit=20)
            if not candidates:
                return None
            
            # Nếu chỉ có duy nhất 1 kết quả khớp từ database, lấy luôn
            if len(candidates) == 1:
                return candidates[0].so_hieu

            scored = [
                (max(_fuzzy_score(name, c.ten_van_ban or ""), 
                     _fuzzy_score(name, c.so_hieu or "")), c)
                for c in candidates
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best = scored[0]
            if best_score >= min_score:
                return best.so_hieu
        except Exception as e:
            logger.warning("[_resolve_so_hieu] error: %s", e)
        return None

    def _fetch_reference_items(self, main_item: dict, exclude_ids: Optional[set] = None) -> List[dict]:
        meta = main_item.get("metadata") or {}
        ref_ids = _parse_reference_ids(meta)
        if not ref_ids: return []
        main_id = main_item.get("chunk_id")
        exclude = set(exclude_ids or ())
        if main_id: exclude.add(main_id)
        to_fetch = [rid for rid in ref_ids if rid and rid not in exclude and not _is_ancestor_ref(main_id, rid)]
        if not to_fetch: return []
        try:
            ref_chunks = self.chroma_store.get_by_ids(to_fetch)
            return [_chunk_to_item(c) for c in ref_chunks]
        except Exception as e:
            logger.warning("[_fetch_reference_items] failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # 1) search_legal_documents
    # ------------------------------------------------------------------
    def search_legal_documents(self, query: str, top_k: int = 5, include_references: bool = False) -> ToolOutput:
        """Tìm kiếm các điều luật liên quan dựa trên câu hỏi (Vector Search)."""
        tool_name = "search_legal_documents"
        try:
            results = self.retrieval_service.search(query=query, top_k_retrieve=top_k)
            if not results:
                return ToolOutput(tool_name=tool_name, success=False, display_text="Không tìm thấy tài liệu.")
            items = [_chunk_to_item(r, score=(r.score_rerank if r.score_rerank else r.distance)) for r in results]
            if include_references:
                limit = min(self.DEFAULT_MAX_MAIN_WITH_REFS, len(items))
                main_ids = {it.get("chunk_id") for it in items if it.get("chunk_id")}
                for it in items[:limit]:
                    refs = self._fetch_reference_items(it, exclude_ids=main_ids)
                    if refs: it["references"] = refs
            display = "\n".join([f"{i+1}. {it['title']}\n   {(it.get('text') or '')[:200]}..." for i, it in enumerate(items)])
            return ToolOutput(tool_name=tool_name, success=True, items=items, display_text=display)
        except Exception as e:
            return ToolOutput(tool_name=tool_name, success=False, error=str(e), display_text=f"Lỗi: {e}")

    # ------------------------------------------------------------------
    # 2) search_document_metadata (NEW)
    # ------------------------------------------------------------------
    def search_document_metadata(
        self,
        so_hieu: Optional[str] = None,
        ten_van_ban: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 10,
    ) -> ToolOutput:
        """Tìm văn bản theo số hiệu, tên, hoặc loại (Luật, Nghị định...)."""
        tool_name = "search_document_metadata"
        if not self.meta_repo:
            return ToolOutput(tool_name=tool_name, success=False, display_text="Database chưa khởi tạo.")
        try:
            rows = []
            if so_hieu:
                r = self.meta_repo.get_by_so_hieu(so_hieu.strip())
                if r: rows = [r]
            elif ten_van_ban:
                rows = self.meta_repo.search_by_name(ten_van_ban.strip(), limit=limit*2)
                scored = [(max(_fuzzy_score(ten_van_ban, r.ten_van_ban or ""), 
                               _fuzzy_score(ten_van_ban, r.so_hieu or "")), r) for r in rows]
                scored.sort(key=lambda x: x[0], reverse=True)
                rows = [x[1] for x in scored[:limit]]
            elif doc_type:
                rows = self.meta_repo.get_by_loai(doc_type.strip())[:limit]
            
            if not rows:
                return ToolOutput(tool_name=tool_name, success=False, display_text="Không tìm thấy.")
            items = [_metadata_row_to_item(r) for r in rows]
            display = "\n".join([f"{i+1}. {it['title']}" for i, it in enumerate(items)])
            return ToolOutput(tool_name=tool_name, success=True, items=items, display_text=display)
        except Exception as e:
            return ToolOutput(tool_name=tool_name, success=False, error=str(e), display_text=f"Lỗi: {e}")

    # ------------------------------------------------------------------
    # 3) get_specific_article (Enhanced with _resolve_so_hieu)
    # ------------------------------------------------------------------
    def get_specific_article(self, article_block: ArticleBlock, include_references: bool = True) -> ToolOutput:
        """Lấy nội dung chi tiết của một điều/khoản cụ thể."""
        tool_name = "get_specific_article"
        try:
            so_hieu = self._resolve_so_hieu(article_block)
            where_filter = chroma_filter_from_article_block(article_block, so_hieu)
            if not where_filter:
                return ToolOutput(tool_name=tool_name, success=False, display_text="Thiếu thông tin tra cứu.")
            results = self.chroma_store.query(ChromaQueryRequest(query_vector=[0.0]*768, top_k=1, filter=where_filter))
            if not results:
                return ToolOutput(tool_name=tool_name, success=False, display_text="Không tìm thấy.")
            item = _chunk_to_item(results[0])
            if include_references:
                refs = self._fetch_reference_items(item, exclude_ids={item.get("chunk_id")})
                if refs: item["references"] = refs
            display = f"**{item['title']}**\n\n{item['text']}"
            return ToolOutput(tool_name=tool_name, success=True, items=[item], display_text=display)
        except Exception as e:
            return ToolOutput(tool_name=tool_name, success=False, error=str(e), display_text=f"Lỗi: {e}")

    def find_cross_references(self, article_block: Optional[ArticleBlock] = None, chunk_id: Optional[str] = None) -> ToolOutput:
        """Lấy các chunk được tham chiếu bởi một chunk gốc."""
        tool_name = "find_cross_references"
        try:
            source_chunk = None
            if chunk_id:
                hits = self.chroma_store.get_by_ids([chunk_id])
                source_chunk = hits[0] if hits else None
            elif article_block:
                so_hieu = self._resolve_so_hieu(article_block)
                wf = chroma_filter_from_article_block(article_block, so_hieu)
                if wf:
                    hits = self.chroma_store.query(ChromaQueryRequest(query_vector=[0.0]*768, top_k=1, filter=wf))
                    source_chunk = hits[0] if hits else None
            
            if not source_chunk:
                return ToolOutput(tool_name=tool_name, success=False, display_text="Không tìm thấy gốc.")
            
            item = _chunk_to_item(source_chunk)
            refs = self._fetch_reference_items(item)
            if refs: item["references"] = refs
            display = f"Tìm thấy {len(refs)} tham chiếu chéo."
            return ToolOutput(tool_name=tool_name, success=True, items=[item], display_text=display)
        except Exception as e:
            return ToolOutput(tool_name=tool_name, success=False, error=str(e), display_text=f"Lỗi: {e}")

    def get_tools_list(self) -> List[StructuredTool]:
        methods = [self.search_legal_documents, self.search_document_metadata, self.get_specific_article, self.find_cross_references]
        return [StructuredTool.from_function(func=m, name=m.__name__, description=m.__doc__) for m in methods]
