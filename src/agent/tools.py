"""
LangChain Tools - Các công cụ cho Agent sử dụng
"""

import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from langchain_core.tools import StructuredTool

from src.search.retrieval import RetrievalService
from src.search.pipeline import SearchPipeline
from src.indexing.vector_store import ChromaStore, ChromaQueryRequest
from src.indexing.embedding import OnnxEmbeddingModel
from src.agent.schemas import ArticleBlock
from src.system.database.db_respository import (
    DocumentMetadataRepository,
    DocumentRelationRepository,
)

logger = logging.getLogger(__name__)

class LegalDocumentTools:
    """Tập hợp các tools cho Legal Document Agent"""
    
    def __init__(
        self,
        chroma_store: ChromaStore,
        embedding_model: OnnxEmbeddingModel,
        db_session: Optional[Session] = None,
        retrieval_service: Optional[SearchPipeline] = None,
    ):
        self.chroma_store = chroma_store
        self.db_session = db_session
        self.retrieval_service = retrieval_service or SearchPipeline(chroma_store, embedding_model)
        
        # Khởi tạo các Repo một lần duy nhất nếu có database session
        self.meta_repo = DocumentMetadataRepository(db_session) if db_session else None
        self.rel_repo = DocumentRelationRepository(db_session) if db_session else None

    def search_legal_documents(self, query: str, top_k: int = 5, filter_by_type: Optional[List[str]] = None) -> str:
        """Tìm kiếm các điều luật, khoản liên quan dựa trên câu hỏi (Vector Search)."""
        try:
            # SearchPipeline.search() takes query string and parameters, not ChromaQueryRequest
            results = self.retrieval_service.search(
                query=query,
                top_k=top_k,
                filter_by_type=filter_by_type or ['dieu', 'khoan', 'diem']
            )
            if not results: return "Không tìm thấy tài liệu liên quan."
            
            # Use score_rerank if available (from reranker), otherwise distance
            output = []
            for i, r in enumerate(results, 1):
                # Build title from metadata fields (van_ban, dieu, khoan, diem)
                meta = r.metadata or {}
                title_parts = []
                if meta.get('dieu'):
                    title_parts.append(f"Điều {meta.get('dieu')}")
                if meta.get('khoan'):
                    title_parts.append(f"Khoản {meta.get('khoan')}")
                if meta.get('diem'):
                    title_parts.append(f"Điểm {meta.get('diem')}")
                
                title = " ".join(title_parts) if title_parts else "Điều khoản"
                
                # Get score for display
                score = r.score_rerank if r.score_rerank is not None else r.distance
                score_text = f"{score:.4f}" if score else "N/A"
                
                # Show more content (200 chars instead of 100)
                output.append(
                    f"{i}. {title}\n"
                    f"   Nội dung: {r.text[:200]}...\n"
                    f"   Độ liên quan: {score_text}"
                )
            return "\n".join(output)
        except Exception as e: return f"Lỗi tìm kiếm: {e}"

    def search_document_metadata(self, doc_type: Optional[str] = None, org_unit: Optional[str] = None) -> str:
        """Tìm tài liệu theo loại, cơ quan ban hành."""
        if not self.meta_repo: return "Lỗi: Database session chưa khởi tạo."
        try:
            results = self.meta_repo.get_by_loai(doc_type) if doc_type else self.meta_repo.get_all(limit=20)
            
            if org_unit:
                results = [r for r in results if r.co_quan_ban_hanh and org_unit.lower() in r.co_quan_ban_hanh.lower()]
            
            if not results: return "Không tìm thấy tài liệu nào phù hợp."
            
            output = [f"Tìm thấy {len(results)} tài liệu:"]
            output.extend([f"{i}. {r.ten_van_ban} ({r.so_hieu}) - {r.loai}" for i, r in enumerate(results, 1)])
            return "\n".join(output)
        except Exception as e: return f"Lỗi: {e}"

    def get_specific_article(self, article_block: ArticleBlock) -> str:
        """Lấy nội dung chi tiết của một điều/khoản cụ thể."""
        try:
            # Tạo filter ngắn gọn bằng dict comprehension: chỉ lấy các field có giá trị
            filter_data = {
                'dieu': article_block.dieu, 'khoan': article_block.khoan, 
                'diem': article_block.diem, 'van_ban': article_block.document_name
            }
            where_filter = {k: v for k, v in filter_data.items() if v}
            if not where_filter: return "Không đủ thông tin để tìm kiếm."

            results = self.chroma_store.query(ChromaQueryRequest(query_vector=[0.0]*768, top_k=1, filter=where_filter))
            if not results: return "Không tìm thấy điều khoản."

            metadata = results[0].metadata or {}
            title = " ".join([f"{k.capitalize()} {metadata[k]}" for k in ['dieu', 'khoan', 'diem'] if k in metadata])
            
            return f"**{title or 'Điều khoản'}**\n\n{results[0].text}\n\nNguồn: {metadata.get('van_ban', 'N/A')}"
        except Exception as e: return f"Lỗi: {e}"

    def find_related_documents(self, doc_id: str, relation_type: Optional[str] = None) -> str:
        """Tìm các văn bản liên quan (sửa đổi, bổ sung, thay thế, v.v.)."""
        if not self.rel_repo: return "Lỗi: Database session chưa khởi tạo."
        try:
            related = self.rel_repo.get_related_documents(doc_id)
            all_rels = (related.get('related_from') or []) + (related.get('related_to') or [])
            
            if relation_type:
                all_rels = [r for r in all_rels if r.relation_type and r.relation_type.value == relation_type]
            
            if not all_rels: return "Không tìm thấy văn bản liên quan."

            output = [f"Tìm thấy {len(all_rels)} tài liệu liên quan:"]
            for i, rel in enumerate(all_rels, 1):
                target_id = rel.entity_end if rel.entity_start == doc_id else rel.entity_start
                target_doc = self.meta_repo.get_by_so_hieu(target_id)
                if target_doc:
                    rel_name = rel.relation_type.value if rel.relation_type else "N/A"
                    output.append(f"{i}. {target_doc.so_hieu}: {target_doc.ten_van_ban} (Quan hệ: {rel_name})")
            
            return "\n".join(output)
        except Exception as e: return f"Lỗi: {e}"

    def find_cross_references(self, article_block: ArticleBlock) -> str:
        """Tìm tất cả các điều, khoản khác tham chiếu đến điều này."""
        try:
            filter_data = {
                'dieu': article_block.dieu, 'khoan': article_block.khoan, 
                'diem': article_block.diem, 'van_ban': article_block.document_name
            }
            where_filter = {k: v for k, v in filter_data.items() if v}
            if not where_filter: return "Không đủ thông tin để tìm kiếm."

            source_chunks = self.chroma_store.query(ChromaQueryRequest(query_vector=[0.0]*768, top_k=1, filter=where_filter))
            if not source_chunks: return "Không tìm thấy điều khoản gốc."

            source_chunk = source_chunks[0]
            ref_ids = [ref for ref in source_chunk.metadata.get('reference', []) if not source_chunk.chunk_id.startswith(ref)]
            if not ref_ids: return "Không có tham chiếu chéo."

            referenced_chunks = self.chroma_store.get_by_ids(ref_ids)
            if not referenced_chunks: return "Không thể lấy nội dung tham chiếu."

            output = [f"Tìm thấy {len(referenced_chunks)} tham chiếu:"]
            output.extend([f"{i}. {c.text[:150]}..." for i, c in enumerate(referenced_chunks, 1)])
            return "\n".join(output)
        except Exception as e: return f"Lỗi: {e}"

    def get_tools_list(self) -> List:
        """Lấy danh sách các công cụ đã được bọc thành LangChain Tool."""
        # Gom tất cả các hàm chức năng vào một mảng
        methods = [
            self.search_legal_documents,
            self.search_document_metadata,
            self.get_specific_article,
            self.find_related_documents,
            self.find_cross_references
        ]
        
        # Tự động biến đổi method thành Tool và xử lý triệt để lỗi 'self'
        return [
            StructuredTool.from_function(
                func=method,
                name=method.__name__,
                description=method.__doc__
            ) 
            for method in methods
        ]