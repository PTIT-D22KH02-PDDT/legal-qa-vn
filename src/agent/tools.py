"""
LangChain Tools - Các công cụ cho Agent sử dụng
"""

import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from langchain_core.tools import tool

from src.search.retrieval import RetrievalService
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
        retrieval_service: Optional[RetrievalService] = None,
    ):
        """
        Khởi tạo tools
        
        Args:
            chroma_store: ChromaStore instance
            embedding_model: Embedding model instance
            db_session: SQLAlchemy database session (cho metadata/relation queries)
            retrieval_service: Retrieval service instance (nếu có)
        """
        self.chroma_store = chroma_store
        self.embedding_model = embedding_model
        self.db_session = db_session
        self.retrieval_service = retrieval_service or RetrievalService(
            chroma_store=chroma_store,
            embedding_model=embedding_model,
        )
    
    def _impl_search_legal_documents(
        self,
        query: str,
        top_k: int = 5,
        filter_by_type: Optional[List[str]] = None,
    ) -> str:
        """
        Tìm kiếm các điều luật, khoản liên quan dựa trên câu hỏi.
        Sử dụng vector similarity search (ChromaDB).
        
        Args:
            query: Câu hỏi hoặc mô tả cần tìm
            top_k: Số lượng kết quả trả về (mặc định: 5)
            filter_by_type: Lọc theo loại điều/khoản (dieu, khoan, diem)
        
        Returns:
            JSON string chứa danh sách tài liệu liên quan
        """
        try:
            logger.info(f"[Tool] Searching documents for query: {query[:50]}...")
            
            # Build request
            request = ChromaQueryRequest(
                query=query,
                n_results=top_k,
                filter_by_type=filter_by_type or ['dieu', 'khoan', 'diem'],
            )
            
            # Execute retrieval
            results = self.retrieval_service.retrieve(request)
            
            if not results:
                return "Không tìm thấy tài liệu liên quan."
            
            # Format results
            output = []
            for i, result in enumerate(results, 1):
                output.append(
                    f"{i}. {result.metadata.get('title', 'N/A')}\n"
                    f"   Nội dung: {result.text[:100]}...\n"
                    f"   Độ tương tự: {result.similarity_score:.2f}"
                )
            
            logger.info(f"[Tool] Found {len(results)} results")
            return "\n".join(output)
        
        except Exception as e:
            logger.error(f"[Tool] Error in search_legal_documents: {e}")
            return f"Lỗi khi tìm kiếm: {str(e)}"
    
    def _impl_search_document_metadata(
        self,
        doc_type: Optional[str] = None,
        org_unit: Optional[str] = None,
    ) -> str:
        """
        Tìm tài liệu theo loại, cơ quan ban hành.
        Truy vấn trực tiếp từ SQLite database (document_metadata table).
        
        Args:
            doc_type: Loại văn bản (e.g., "Luật", "Nghị định", "Quyết định")
            org_unit: Cơ quan ban hành (tuỳ chọn)
        
        Returns:
            Danh sách metadata của các tài liệu tìm được
        """
        try:
            if not self.db_session:
                return "Lỗi: Database session không được khởi tạo."
            
            logger.info(f"[Tool] Searching metadata: type={doc_type}, org={org_unit}")
            
            # Query từ SQLite database
            repo = DocumentMetadataRepository(self.db_session)
            
            if doc_type:
                # Tìm theo loại văn bản
                results = repo.get_by_loai(doc_type)
                logger.info(f"[Tool] Found {len(results)} documents with type={doc_type}")
            else:
                # Lấy tất cả
                results = repo.get_all(limit=20)
                logger.info(f"[Tool] Found {len(results)} documents")
            
            if not results:
                return f"Không tìm thấy {doc_type or 'tài liệu'} nào."
            
            # Filter theo cơ quan ban hành nếu có
            if org_unit:
                results = [
                    r for r in results 
                    if r.co_quan_ban_hanh and org_unit.lower() in r.co_quan_ban_hanh.lower()
                ]
            
            if not results:
                return f"Không tìm thấy tài liệu loại {doc_type} của {org_unit}."
            
            # Format results
            output = [f"Tìm thấy {len(results)} tài liệu:"]
            for i, result in enumerate(results, 1):
                output.append(
                    f"{i}. {result.ten_van_ban} ({result.so_hieu})\n"
                    f"   Loại: {result.loai}\n"
                    f"   Cơ quan: {result.co_quan_ban_hanh or 'N/A'}\n"
                    f"   Ngày ban hành: {result.ngay_ban_hanh or 'N/A'}\n"
                    f"   Số điều: {result.so_dieu}"
                )
            
            return "\n".join(output)
        
        except Exception as e:
            logger.error(f"[Tool] Error in search_document_metadata: {e}")
            return f"Lỗi: {str(e)}"
    
    def _impl_get_specific_article(
        self,
        article_block: ArticleBlock,
    ) -> str:
        """
        Lấy nội dung chi tiết của một điều/khoản cụ thể.
        Nhận ArticleBlock từ QueryAnalysisResult.extracted_blocks.
        Tìm trực tiếp theo metadata, không dùng embedding.
        
        Args:
            article_block: ArticleBlock chứa (dieu, khoan, diem, chuong, document_name)
        
        Returns:
            Nội dung đầy đủ của điều khoản
        """
        try:
            # Trích các thuộc tính từ ArticleBlock
            dieu_number = article_block.dieu
            khoan_number = article_block.khoan
            diem_name = article_block.diem
            document_name = article_block.document_name
            
            # Build metadata filter
            where_filter = {}
            
            if dieu_number:
                where_filter['dieu'] = dieu_number
            if khoan_number:
                where_filter['khoan'] = khoan_number
            if diem_name:
                where_filter['diem'] = diem_name
            if document_name:
                where_filter['van_ban'] = document_name
            
            if not where_filter:
                return "ArticleBlock không có thông tin để tìm kiếm."
            
            # Build log message
            filter_info = ", ".join([f"{k}={v}" for k, v in where_filter.items()])
            logger.info(f"[Tool] Getting article with filter: {filter_info}")
            
            # Query ChromaDB với metadata filter
            # Dùng dummy vector (zeros) vì chỉ cần filter by metadata, không dùng embedding
            dummy_vector = [0.0] * 768  # Size phải match embedding dimension
            request = ChromaQueryRequest(
                query_vector=dummy_vector,
                n_results=1,
                filter=where_filter if where_filter else None,
            )
            
            results = self.chroma_store.query(request)
            
            if not results:
                return f"Không tìm thấy với filter: {filter_info}"
            
            # Return first result
            result = results[0]
            metadata = result.metadata or {}
            
            # Build display info từ metadata
            display_parts = []
            if 'dieu' in metadata:
                display_parts.append(f"Điều {metadata['dieu']}")
            if 'khoan' in metadata:
                display_parts.append(f"Khoản {metadata['khoan']}")
            if 'diem' in metadata:
                display_parts.append(f"Điểm {metadata['diem']}")
            
            display = " ".join(display_parts) or "Điều khoản"
            
            output = f"**{display}**\n\n"
            output += result.text + "\n\n"
            output += f"Nguồn: {metadata.get('van_ban', 'N/A')}"
            
            logger.info(f"[Tool] Found article: {filter_info}")
            return output
        
        except Exception as e:
            logger.error(f"[Tool] Error in get_specific_article: {e}")
            return f"Lỗi: {str(e)}"
    
    def _map_relation_type_to_keywords(self, relation_type: str) -> str:
        """Map RelationType enum sang từ khóa tiếng Việt để search"""
        relation_keywords = {
            "huong_dan_thi_hanh": "hướng dẫn thực hiện thi hành",
            "sua_doi_bo_sung": "sửa đổi bổ sung",
            "thay_the": "thay thế hủy bỏ",
            "bai_bo": "bãi bỏ",
            "dinh_chi_hieu_luc": "đình chỉ hiệu lực",
            "tam_thoi_ap_dung": "áp dụng thí điểm",
            "giai_thich": "giải thích",
            "lien_quan": "liên quan",
            "tham_chieu": "tham chiếu"
        }
        return relation_keywords.get(relation_type, relation_type)
    
    def _impl_find_related_documents(
        self,
        doc_id: str,
        relation_type: Optional[str] = None,
    ) -> str:
        """
        Tìm các văn bản liên quan (sửa đổi, bổ sung, hủy bỏ, thay thế, ...).
        Truy vấn trực tiếp từ SQLite database (document_relation table).
        
        Args:
            doc_id: Số hiệu văn bản (e.g., "102/2017/NĐ-CP")
            relation_type: Loại liên hệ (sua_doi_bo_sung, thay_the, bai_bo, huong_dan_thi_hanh, etc.)
        
        Returns:
            Danh sách văn bản liên quan
        """
        try:
            if not self.db_session:
                return "Lỗi: Database session không được khởi tạo."
            
            logger.info(f"[Tool] Finding related documents for {doc_id}, relation={relation_type}")
            
            # Query từ SQLite database
            relation_repo = DocumentRelationRepository(self.db_session)
            metadata_repo = DocumentMetadataRepository(self.db_session)
            
            # Lấy tất cả quan hệ của văn bản
            related = relation_repo.get_related_documents(doc_id)
            
            all_relations = []
            if related['related_from']:
                all_relations.extend(related['related_from'])
            if related['related_to']:
                all_relations.extend(related['related_to'])
            
            if not all_relations:
                return f"Không tìm thấy tài liệu liên quan đến {doc_id}."
            
            # Filter theo loại quan hệ nếu có
            if relation_type:
                all_relations = [
                    r for r in all_relations
                    if r.relation_type and r.relation_type.value == relation_type
                ]
            
            if not all_relations:
                return f"Không tìm thấy quan hệ '{relation_type}' của {doc_id}."
            
            # Format results
            output = [f"Tìm thấy {len(all_relations)} tài liệu liên quan:"]
            
            for i, rel in enumerate(all_relations, 1):
                # Xác định văn bản target
                target_id = rel.entity_end if rel.entity_start == doc_id else rel.entity_start
                target_doc = metadata_repo.get_by_so_hieu(target_id)
                
                if target_doc:
                    relation_name = rel.relation_type.value if rel.relation_type else "N/A"
                    output.append(
                        f"{i}. {target_doc.so_hieu}: {target_doc.ten_van_ban}\n"
                        f"   Loại quan hệ: {relation_name}\n"
                        f"   Loại văn bản: {target_doc.loai}\n"
                        f"   Ngày ban hành: {target_doc.ngay_ban_hanh or 'N/A'}"
                    )
            
            logger.info(f"[Tool] Found {len(all_relations)} related documents")
            return "\n".join(output)
        
        except Exception as e:
            logger.error(f"[Tool] Error in find_related_documents: {e}")
            return f"Lỗi: {str(e)}"
    
    def _impl_find_cross_references(
        self,
        article_block: ArticleBlock,
    ) -> str:
        """
        Tìm tất cả các điều, khoản khác tham chiếu đến điều này.
        Lấy danh sách reference IDs từ metadata chunk, rồi query ChromaDB để lấy các chunks.
        Args:
            article_block: ArticleBlock chứa (dieu, khoan, diem, document_name)
                          Metadata của block sẽ chứa 'reference' field là danh sách chunk IDs
        
        Returns:
            Danh sách các tham chiếu chéo với nội dung đầy đủ
        """
        try:
            # Trích các thuộc tính từ ArticleBlock để log
            article_info = f"Điều {article_block.dieu}"
            if article_block.khoan:
                article_info += f" Khoản {article_block.khoan}"
            if article_block.diem:
                article_info += f" Điểm {article_block.diem}"
            
            logger.info(f"[Tool] Finding cross-references for {article_info}")
            
            # Build filter để tìm chunk này
            where_filter = {}
            if article_block.dieu:
                where_filter['dieu'] = article_block.dieu
            if article_block.khoan:
                where_filter['khoan'] = article_block.khoan
            if article_block.diem:
                where_filter['diem'] = article_block.diem
            if article_block.document_name:
                where_filter['van_ban'] = article_block.document_name
            
            if not where_filter:
                return "ArticleBlock không có thông tin để tìm kiếm."
            
            # Tìm chunk này trong ChromaDB
            # Dùng dummy vector vì chỉ cần filter by metadata
            dummy_vector = [0.0] * 768  # Size phải match embedding dimension
            request = ChromaQueryRequest(
                query_vector=dummy_vector,
                n_results=1,
                filter=where_filter if where_filter else None,
            )
            
            source_chunks = self.chroma_store.query(request)
            
            if not source_chunks:
                return f"Không tìm thấy {article_info} trong database."
            
            source_chunk = source_chunks[0]
            metadata = source_chunk.metadata or {}
            
            # Lấy danh sách reference IDs từ metadata
            # Reference field sẽ là list of chunk IDs (được set khi indexing)
            reference_ids = metadata.get('reference', [])
            reference_ids = [ref for ref in reference_ids if not source_chunk.chunk_id.startswith(ref)]
            if not reference_ids:
                return f"{article_info} không có tham chiếu đến bất kỳ điều khoản nào khác."
            
            # Query ChromaDB để lấy các chunks được referenced
            referenced_chunks = self.chroma_store.get_by_ids(reference_ids)
            
            if not referenced_chunks:
                return f"Không thể lấy nội dung của các tham chiếu của {article_info}."
            
            # Format results
            output = [f"Tìm thấy {len(referenced_chunks)} tham chiếu chéo từ {article_info}:"]
            for i, chunk in enumerate(referenced_chunks, 1):
                metadata = chunk.metadata or {}
                output.append(
                    f"{i}. Điều {metadata.get('dieu', '-')} "
                    f"Khoản {metadata.get('khoan', '-')} "
                    f"Điểm {metadata.get('diem', '-')} "
                    f"({metadata.get('van_ban', 'N/A')})\n"
                    f"   Nội dung: {chunk.text[:150]}..."
                )
            
            logger.info(f"[Tool] Found {len(referenced_chunks)} cross-references")
            return "\n".join(output)
        
        except Exception as e:
            logger.error(f"[Tool] Error in find_cross_references: {e}")
            return f"Lỗi: {str(e)}"
    
    def get_tools_list(self) -> List:
        """
        Lấy danh sách tất cả các tools dưới dạng LangChain Tool objects
        Tạo standalone functions với @tool decorator để tránh vấn đề với instance methods
        Returns:
            List các LangChain tools
        """
        # Tool 1: search_legal_documents
        @tool
        def search_legal_documents(
            query: str,
            top_k: int = 5,
            filter_by_type: Optional[List[str]] = None,
        ) -> str:
            """Tìm kiếm các điều luật, khoản liên quan dựa trên câu hỏi.
            Sử dụng vector similarity search (ChromaDB).
            """
            return self._impl_search_legal_documents(query, top_k, filter_by_type)
        
        # Tool 2: search_document_metadata
        @tool
        def search_document_metadata(
            doc_type: Optional[str] = None,
            org_unit: Optional[str] = None,
        ) -> str:
            """Tìm tài liệu theo loại, cơ quan ban hành."""
            return self._impl_search_document_metadata(doc_type, org_unit)
        
        # Tool 3: get_specific_article
        @tool
        def get_specific_article(
            article_block: ArticleBlock,
        ) -> str:
            """Lấy nội dung chi tiết của một điều/khoản cụ thể."""
            return self._impl_get_specific_article(article_block)
        
        # Tool 4: find_related_documents
        @tool
        def find_related_documents(
            doc_id: str,
            relation_type: Optional[str] = None,
        ) -> str:
            """Tìm các văn bản liên quan."""
            return self._impl_find_related_documents(doc_id, relation_type)
        
        # Tool 5: find_cross_references
        @tool
        def find_cross_references(
            article_block: ArticleBlock,
        ) -> str:
            """Tìm tất cả các điều, khoản khác tham chiếu đến điều này."""
            return self._impl_find_cross_references(article_block)
        
        return [
            search_legal_documents,
            search_document_metadata,
            get_specific_article,
            find_related_documents,
            find_cross_references,
        ]