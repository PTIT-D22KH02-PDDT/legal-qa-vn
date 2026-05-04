"""
LangChain Tools cho Legal Document Agent.

Tất cả tool đều trả về `ToolOutput` (xem schemas.py) gồm:
- `items`: list chunk/metadata với metadata đầy đủ.
- `display_text`: text đã format, đưa trực tiếp vào prompt LLM.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool

from src.indexing.embedding.remote_embedding import RemoteEmbeddingModel
from src.indexing.embedding.utils import SECTION_TYPE_NAMES as _SECTION_LABELS
from src.indexing.vector_store import ChromaQueryRequest, ChromaStore
from src.search.search import SearchService

from ..schemas import ArticleBlock, ToolOutput
from ..utils.chroma_metadata import chroma_filter_from_article_block

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
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
    """Tập hợp các tools cho Legal Document Agent (không phụ thuộc Database)."""

    DEFAULT_MAX_MAIN_WITH_REFS = 2

    def __init__(
        self,
        chroma_store: ChromaStore,
        embedding_model: RemoteEmbeddingModel,
        llm=None,
        retrieval_service: Optional[SearchService] = None,
        **kwargs,  # bỏ qua các tham số cũ như db_session
    ):
        self.chroma_store = chroma_store
        self.retrieval_service = retrieval_service or SearchService(
            chroma_store, embedding_model
        )

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------
    def _fetch_reference_items(
        self,
        main_item: dict,
        exclude_ids: Optional[set] = None,
    ) -> List[dict]:
        meta = main_item.get("metadata") or {}
        ref_ids = _parse_reference_ids(meta)
        if not ref_ids:
            return []
        main_id = main_item.get("chunk_id")
        exclude = set(exclude_ids or ())
        if main_id:
            exclude.add(main_id)
        to_fetch = [
            rid for rid in ref_ids
            if rid and rid not in exclude and not _is_ancestor_ref(main_id, rid)
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
    # 1) search_legal_documents
    # ------------------------------------------------------------------
    def search_legal_documents(
        self,
        query: str,
        top_k: int = 5,
        filter_by_type: Optional[List[str]] = None,
        include_references: bool = False,
        max_main_with_refs: Optional[int] = None,
    ) -> ToolOutput:
        """Tìm kiếm các điều luật, khoản liên quan dựa trên câu hỏi (Vector Search)."""
        tool_name = "search_legal_documents"
        try:
            results = self.retrieval_service.search(
                query=query,
                top_k_retrieve=top_k,
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

            if include_references:
                limit = max_main_with_refs if max_main_with_refs is not None else self.DEFAULT_MAX_MAIN_WITH_REFS
                limit = max(0, min(limit, len(items)))
                main_ids = {it.get("chunk_id") for it in items if it.get("chunk_id")}
                for it in items[:limit]:
                    refs = self._fetch_reference_items(it, exclude_ids=main_ids)
                    if refs:
                        it["references"] = refs

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
    # 2) get_specific_article
    # ------------------------------------------------------------------
    def get_specific_article(
        self,
        article_block: ArticleBlock,
        include_references: bool = True,
    ) -> ToolOutput:
        """Lấy nội dung chi tiết của một điều/khoản cụ thể theo số hiệu."""
        tool_name = "get_specific_article"
        try:
            so_hieu = (article_block.so_hieu or "").strip() or None
            where_filter = chroma_filter_from_article_block(article_block, so_hieu)
            if not where_filter:
                return ToolOutput(
                    tool_name=tool_name, success=False,
                    display_text="Không đủ thông tin (cần ít nhất dieu/khoan/diem hoặc so_hieu).",
                )

            results = self.chroma_store.query(ChromaQueryRequest(
                query_vector=[0.0] * 768, top_k=1, filter=where_filter,
            ))
            if not results:
                return ToolOutput(
                    tool_name=tool_name, success=False, items=[],
                    display_text="Không tìm thấy điều khoản.",
                )

            item = _chunk_to_item(results[0])
            if include_references:
                refs = self._fetch_reference_items(
                    item, exclude_ids={item.get("chunk_id")} if item.get("chunk_id") else None,
                )
                if refs:
                    item["references"] = refs

            display = (
                f"**{item['title']}**\n\n{item['text']}\n\n"
                f"Nguồn: {item.get('so_hieu') or 'N/A'}"
            )
            for j, ref in enumerate(item.get("references") or [], 1):
                display += (
                    f"\n\n---\n**Tham chiếu {j}.** {ref.get('title', 'Chunk')}\n"
                    f"{(ref.get('text') or '')[:1200]}"
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
    # 3) find_cross_references
    # ------------------------------------------------------------------
    def find_cross_references(
        self,
        article_block: Optional[ArticleBlock] = None,
        chunk_id: Optional[str] = None,
    ) -> ToolOutput:
        """Lấy các chunk được tham chiếu bởi một chunk gốc."""
        tool_name = "find_cross_references"
        try:
            source_chunk = None
            if chunk_id:
                hits = self.chroma_store.get_by_ids([chunk_id])
                source_chunk = hits[0] if hits else None
            elif article_block is not None:
                so_hieu = (article_block.so_hieu or "").strip() or None
                where_filter = chroma_filter_from_article_block(article_block, so_hieu)
                if not where_filter:
                    return ToolOutput(
                        tool_name=tool_name, success=False,
                        display_text="Không đủ thông tin để xác định chunk gốc.",
                    )
                hits = self.chroma_store.query(ChromaQueryRequest(
                    query_vector=[0.0] * 768, top_k=1, filter=where_filter,
                ))
                source_chunk = hits[0] if hits else None
            else:
                return ToolOutput(
                    tool_name=tool_name, success=False,
                    display_text="Cần truyền `article_block` hoặc `chunk_id`.",
                )

            if source_chunk is None:
                return ToolOutput(tool_name=tool_name, success=False, items=[], display_text="Không tìm thấy chunk gốc.")

            source_item = _chunk_to_item(source_chunk)
            source_id = source_item.get("chunk_id")
            ref_ids = _parse_reference_ids(source_chunk.metadata)
            ref_ids = [
                rid for rid in ref_ids
                if rid and rid != source_id and not _is_ancestor_ref(source_id, rid)
            ]
            if not ref_ids:
                return ToolOutput(
                    tool_name=tool_name, success=True, items=[source_item],
                    display_text=f"Chunk gốc **{source_item['title']}** không tham chiếu tới chunk nào khác.",
                )

            ref_chunks = self.chroma_store.get_by_ids(ref_ids)
            if not ref_chunks:
                return ToolOutput(
                    tool_name=tool_name, success=False, items=[source_item],
                    display_text=f"Tìm thấy {len(ref_ids)} chunk_id tham chiếu nhưng không load được nội dung.",
                )

            ref_items = [_chunk_to_item(c) for c in ref_chunks]
            source_item["references"] = ref_items
            display = [
                f"Chunk gốc **{source_item['title']}** tham chiếu tới {len(ref_items)} chunk:"
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
            self.get_specific_article,
            self.find_cross_references,
        ]
        return [
            StructuredTool.from_function(
                func=method, name=method.__name__, description=method.__doc__,
            )
            for method in methods
        ]
