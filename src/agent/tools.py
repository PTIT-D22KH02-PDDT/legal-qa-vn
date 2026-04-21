"""
LangChain Tools - Các công cụ cho Agent sử dụng
"""

import logging
from typing import List,Optional
from langchain_core.tools import tool

from src.search.retrieval import RetrievalService
from src.indexing.vector_store import ChromaStore, ChromaQueryRequest
from src.indexing.embedding import OnnxEmbeddingModel
logger = logging.getLogger(__name__)


class LegalDocumentTools:
    """Tập hợp các tools cho Legal Document Agent"""
    
    def __init__(
        self,
        chroma_store: ChromaStore,
        embedding_model: OnnxEmbeddingModel,
        retrieval_service: Optional[RetrievalService] = None,
    ):
        """
        Khởi tạo tools
        
        Args:
            chroma_store: ChromaStore instance
            embedding_model: Embedding model instance
            retrieval_service: Retrieval service instance (nếu có)
        """
        self.chroma_store = chroma_store
        self.embedding_model = embedding_model
        self.retrieval_service = retrieval_service or RetrievalService(
            chroma_store=chroma_store,
            embedding_model=embedding_model,
        )
    
    @tool
    def search_legal_documents(
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
    
    @tool
    def search_document_metadata(
        self,
        doc_type: Optional[str] = None,
        org_unit: Optional[str] = None,
        year: Optional[int] = None,
    ) -> str:
        """
        Tìm tài liệu theo loại, cơ quan ban hành, năm ban hành.
        Truy vấn từ metadata trong database.
        
        Args:
            doc_type: Loại văn bản (e.g., "Luật", "Nghị định", "Quyết định")
            org_unit: Cơ quan ban hành (tuỳ chọn)
            year: Năm ban hành (tuỳ chọn)
        
        Returns:
            JSON string chứa danh sách metadata của các tài liệu
        """
        try:
            logger.info(f"[Tool] Searching metadata: type={doc_type}, org={org_unit}, year={year}")
            
            # Construct query to ChromaDB (filter by metadata)
            filters = {}
            if doc_type:
                filters['loai'] = doc_type
            if org_unit:
                filters['co_quan_ban_hanh'] = org_unit
            if year:
                filters['year'] = year
            
            # Query ChromaDB với filter
            request = ChromaQueryRequest(
                query=f"Loại: {doc_type or 'Tất cả'}",
                n_results=20,
                where=filters if filters else None,
            )
            
            results = self.chroma_store.query(request)
            
            if not results:
                return f"Không tìm thấy {doc_type or 'tài liệu'} nào."
            
            # Format results
            output = []
            for i, result in enumerate(results, 1):
                metadata = result.metadata or {}
                output.append(
                    f"{i}. {metadata.get('ten_van_ban', 'N/A')} ({metadata.get('so_hieu', 'N/A')})\n"
                    f"   Loại: {metadata.get('loai', 'N/A')}\n"
                    f"   Cơ quan: {metadata.get('co_quan_ban_hanh', 'N/A')}\n"
                    f"   Ngày ban hành: {metadata.get('ngay_ban_hanh', 'N/A')}"
                )
            
            logger.info(f"[Tool] Found {len(results)} documents")
            return "\n".join(output)
        
        except Exception as e:
            logger.error(f"[Tool] Error in search_document_metadata: {e}")
            return f"Lỗi khi tìm metadata: {str(e)}"
    
    @tool
    def get_specific_article(
        self,
        article_number: int,
        document_name: Optional[str] = None,
    ) -> str:
        """
        Lấy nội dung chi tiết của một điều, khoản cụ thể.
        Ví dụ: Điều 5 của Luật 102/2017
        
        Args:
            article_number: Số điều
            document_name: Tên văn bản (tuỳ chọn, để tìm chính xác hơn)
        
        Returns:
            Nội dung đầy đủ của điều khoản
        """
        try:
            logger.info(f"[Tool] Getting article {article_number} from {document_name or 'all documents'}")
            
            # Build query for specific article
            if document_name:
                query = f"Điều {article_number} {document_name}"
            else:
                query = f"Điều {article_number}"
            
            request = ChromaQueryRequest(
                query=query,
                n_results=3,
                filter_by_type=['dieu'],  # Chỉ lấy điều
            )
            
            results = self.retrieval_service.retrieve(request)
            
            if not results:
                return f"Không tìm thấy Điều {article_number}."
            
            # Format kết quả
            result = results[0]  # Lấy kết quả đầu tiên (có score cao nhất)
            output = f"**Điều {article_number}**\n\n"
            output += result.text + "\n\n"
            output += f"Nguồn: {result.metadata.get('title', 'N/A')}"
            
            logger.info(f"[Tool] Found article {article_number}")
            return output
        
        except Exception as e:
            logger.error(f"[Tool] Error in get_specific_article: {e}")
            return f"Lỗi khi lấy điều {article_number}: {str(e)}"
    
    @tool
    def find_related_documents(
        self,
        doc_id: str,
        relation_type: Optional[str] = None,
    ) -> str:
        """
        Tìm các văn bản liên quan (sửa đổi, bổ sung, hủy bỏ, thay thế, ...).
        Sử dụng relationship graph từ database.
        
        Args:
            doc_id: ID của tài liệu
            relation_type: Loại liên hệ (amends, supersedes, voids, supplements)
        
        Returns:
            Danh sách tài liệu liên quan
        """
        try:
            logger.info(f"[Tool] Finding related documents for {doc_id}, relation={relation_type}")
            
            # TODO: Query database để lấy mối quan hệ giữa các tài liệu
            # Hiện tại chỉ là placeholder
            
            output = f"Tìm kiếm tài liệu liên quan đến {doc_id}...\n\n"
            output += "Chức năng này sẽ được hoàn thiện với database integration.\n"
            output += f"Loại liên hệ: {relation_type or 'Tất cả'}"
            
            logger.info(f"[Tool] Relationship lookup for {doc_id}")
            return output
        
        except Exception as e:
            logger.error(f"[Tool] Error in find_related_documents: {e}")
            return f"Lỗi khi tìm tài liệu liên quan: {str(e)}"
    
    @tool
    def find_cross_references(
        self,
        article_id: str,
    ) -> str:
        """
        Tìm tất cả các điều, khoản khác tham chiếu đến điều này.
        Giúp hiểu bối cảnh pháp lý toàn diện.
        
        Args:
            article_id: ID của điều/khoản (ví dụ: "dieu_5_102_2017")
        
        Returns:
            Danh sách các tham chiếu chéo
        """
        try:
            logger.info(f"[Tool] Finding cross-references for {article_id}")
            
            # TODO: Query database để lấy các tham chiếu chéo
            # Hiện tại chỉ là placeholder
            
            output = f"Tìm kiếm tham chiếu chéo cho {article_id}...\n\n"
            output += "Chức năng này sẽ được hoàn thiện với database integration.\n"
            output += "Sẽ liệt kê tất cả điều/khoản khác tham chiếu đến điều này."
            
            logger.info(f"[Tool] Cross-reference lookup for {article_id}")
            return output
        
        except Exception as e:
            logger.error(f"[Tool] Error in find_cross_references: {e}")
            return f"Lỗi khi tìm tham chiếu chéo: {str(e)}"
    
    def get_tools_list(self) -> List:
        """
        Lấy danh sách tất cả các tools dưới dạng LangChain Tool objects
        Returns:
            List các LangChain tools
        """
        return [
            self.search_legal_documents,
            self.search_document_metadata,
            self.get_specific_article,
            self.find_related_documents,
            self.find_cross_references,
        ]