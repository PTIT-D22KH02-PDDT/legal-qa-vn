"""
LangChain Tools cho Legal QA Agent.

Toàn bộ tool đều trả về `ToolOutput` (xem `schemas.py`) gồm:
- `items`: list các chunk/metadata/relation với metadata đầy đủ (để downstream
  node như `grade_retrieval` / `validate_answer` đọc được `van_ban`, `dieu`,
  `khoan`, `chunk_id`...).
- `display_text`: bản text đã format, để đưa trực tiếp vào prompt LLM.

Cách này thay thế cho kiểu cũ (trả string thuần) — vốn làm mất metadata,
khiến `_extract_sources` không hoạt động.
"""

from __future__ import annotations

import logging
from typing import List, Optional

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


def _format_chunk_title(meta: dict) -> str:
    parts = []
    if meta.get("dieu"):
        parts.append(f"Điều {meta['dieu']}")
    if meta.get("khoan"):
        parts.append(f"Khoản {meta['khoan']}")
    if meta.get("diem"):
        parts.append(f"Điểm {meta['diem']}")
    title = " ".join(parts) if parts else "Điều khoản"
    van_ban = meta.get("van_ban")
    if van_ban:
        title = f"{title} — {van_ban}"
    return title


def _chunk_to_item(chunk, score=None) -> dict:
    """Convert ChromaQueryResult → dict structured chunk."""
    meta = chunk.metadata or {}
    return {
        "kind": "chunk",
        "chunk_id": getattr(chunk, "chunk_id", None),
        "text": chunk.text,
        "metadata": meta,
        "van_ban": meta.get("van_ban"),
        "dieu": meta.get("dieu"),
        "khoan": meta.get("khoan"),
        "diem": meta.get("diem"),
        "chuong": meta.get("chuong"),
        "score": score,
        "title": _format_chunk_title(meta),
    }


class LegalDocumentTools:
    """Tập hợp các tools cho Legal Document Agent."""

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
    # 1. search_legal_documents
    # ------------------------------------------------------------------
    def search_legal_documents(
        self,
        query: str,
        top_k: int = 5,
        filter_by_type: Optional[List[str]] = None,
    ) -> ToolOutput:
        """Tìm kiếm các điều luật, khoản liên quan dựa trên câu hỏi (Vector Search)."""
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

            items = []
            display_lines = []
            for i, r in enumerate(results, 1):
                score = r.score_rerank if r.score_rerank is not None else r.distance
                item = _chunk_to_item(r, score=score)
                items.append(item)
                score_text = f"{score:.4f}" if score is not None else "N/A"
                display_lines.append(
                    f"{i}. {item['title']}\n"
                    f"   Nội dung: {item['text'][:300]}...\n"
                    f"   Độ liên quan: {score_text}"
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
    # 2. search_document_metadata
    # ------------------------------------------------------------------
    def search_document_metadata(
        self,
        doc_type: Optional[str] = None,
        org_unit: Optional[str] = None,
    ) -> ToolOutput:
        """Tìm tài liệu theo loại, cơ quan ban hành."""
        tool_name = "search_document_metadata"
        if not self.meta_repo:
            return ToolOutput(
                tool_name=tool_name, success=False,
                error="no db session",
                display_text="Lỗi: Database session chưa khởi tạo.",
            )
        try:
            results = (
                self.meta_repo.get_by_loai(doc_type)
                if doc_type
                else self.meta_repo.get_all(limit=20)
            )
            if org_unit:
                results = [
                    r for r in results
                    if r.co_quan_ban_hanh
                    and org_unit.lower() in r.co_quan_ban_hanh.lower()
                ]
            if not results:
                return ToolOutput(
                    tool_name=tool_name, success=False, items=[],
                    display_text="Không tìm thấy tài liệu nào phù hợp.",
                )

            items = [
                {
                    "kind": "metadata",
                    "so_hieu": r.so_hieu,
                    "ten_van_ban": r.ten_van_ban,
                    "loai": r.loai,
                    "co_quan_ban_hanh": r.co_quan_ban_hanh,
                    "ngay_ban_hanh": r.ngay_ban_hanh,
                    "van_ban": r.so_hieu,
                    "title": f"{r.ten_van_ban} ({r.so_hieu})",
                }
                for r in results
            ]
            display = [f"Tìm thấy {len(items)} tài liệu:"] + [
                f"{i}. {it['ten_van_ban']} ({it['so_hieu']}) - {it['loai']}"
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
    # 3. get_specific_article
    # ------------------------------------------------------------------
    def get_specific_article(self, article_block: ArticleBlock) -> ToolOutput:
        """Lấy nội dung chi tiết của một điều/khoản cụ thể."""
        tool_name = "get_specific_article"
        try:
            filter_data = {
                "dieu": article_block.dieu,
                "khoan": article_block.khoan,
                "diem": article_block.diem,
                "van_ban": article_block.document_name,
            }
            where_filter = {k: v for k, v in filter_data.items() if v}
            if not where_filter:
                return ToolOutput(
                    tool_name=tool_name, success=False,
                    display_text="Không đủ thông tin để tìm kiếm.",
                )

            # TODO: thay hack query_vector=[0]*768 bằng ChromaStore.get(where=...)
            results = self.chroma_store.query(ChromaQueryRequest(
                query_vector=[0.0] * 768, top_k=1, filter=where_filter,
            ))
            if not results:
                return ToolOutput(
                    tool_name=tool_name, success=False, items=[],
                    display_text="Không tìm thấy điều khoản.",
                )

            item = _chunk_to_item(results[0])
            display = (
                f"**{item['title']}**\n\n{item['text']}\n\n"
                f"Nguồn: {item.get('van_ban') or 'N/A'}"
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
    # 4. find_related_documents
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
                        "van_ban": target_doc.so_hieu,
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
    # 5. find_cross_references
    # ------------------------------------------------------------------
    def find_cross_references(self, article_block: ArticleBlock) -> ToolOutput:
        """Tìm tất cả các điều, khoản khác tham chiếu đến điều này."""
        tool_name = "find_cross_references"
        try:
            filter_data = {
                "dieu": article_block.dieu,
                "khoan": article_block.khoan,
                "diem": article_block.diem,
                "van_ban": article_block.document_name,
            }
            where_filter = {k: v for k, v in filter_data.items() if v}
            if not where_filter:
                return ToolOutput(
                    tool_name=tool_name, success=False,
                    display_text="Không đủ thông tin để tìm kiếm.",
                )

            source_chunks = self.chroma_store.query(ChromaQueryRequest(
                query_vector=[0.0] * 768, top_k=1, filter=where_filter,
            ))
            if not source_chunks:
                return ToolOutput(
                    tool_name=tool_name, success=False,
                    display_text="Không tìm thấy điều khoản gốc.",
                )

            source_chunk = source_chunks[0]
            refs = source_chunk.metadata.get("reference", []) if source_chunk.metadata else []
            ref_ids = [
                ref for ref in refs
                if not source_chunk.chunk_id.startswith(ref)
            ]
            if not ref_ids:
                return ToolOutput(
                    tool_name=tool_name, success=False, items=[],
                    display_text="Không có tham chiếu chéo.",
                )

            referenced_chunks = self.chroma_store.get_by_ids(ref_ids)
            if not referenced_chunks:
                return ToolOutput(
                    tool_name=tool_name, success=False, items=[],
                    display_text="Không thể lấy nội dung tham chiếu.",
                )

            items = [_chunk_to_item(c) for c in referenced_chunks]
            display = [f"Tìm thấy {len(items)} tham chiếu:"] + [
                f"{i}. {it['title']}: {it['text'][:150]}..."
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
