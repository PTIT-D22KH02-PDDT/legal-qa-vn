from typing import List, Optional, Dict, Any
from src.indexing.vector_store import ChromaConfig, ChromaQueryRequest
from src.schemas import ChromaQueryResult
from src.indexing.embedding import (
    EmbeddingRequest,
    create_embedding_request,
)
from src.indexing.embedding.onnx_embedding import OnnxEmbeddingModel
from .config import RetrievalConfig


_config = RetrievalConfig.get_default_config()
_store_params = _config.get_store_params()

COLLECTION_NAME = _store_params['collection_name']
CHROMA_DB_DIR = _store_params['persist_directory']
EMBEDDING_MODEL_NAME = _config.get_embedding_params()['model_name']

# Chỉ retrieve các leaf nodes (có nội dung thực tế)
# Bỏ qua các container nodes (Phần, Chương, Mục)
LEAF_NODE_TYPES = ['dieu', 'khoan', 'diem']

class RetrievalService:
    """Service chính để retrieve điều khoản từ ChromaDB"""
    
    def __init__(
        self,
        chroma_store,
        embedding_model,
        collection_name: str = "legal_documents"
    ):
        """
        Args:
            chroma_store: ChromaStore instance
            embedding_model: OnnxEmbeddingModel hoặc EmbeddingModel instance
            collection_name: Tên collection trong ChromaDB
        """
        self.chroma_store = chroma_store
        self.embedding_model = embedding_model
        self.collection_name = collection_name

    def _embed_query(self, query: str) -> List[float]:
        """Embed query thành vector"""
        embedding_request = EmbeddingRequest(
            chunk_id=None,
            num_chunk=0,
            text=query,
            metadata={}  # Query không có metadata
        )
        result = self.embedding_model.embed([embedding_request])
        if not result:
            raise ValueError(f"Failed to embed query: {query}")
        return result[0].vector


    def _build_filter_metadata(self, filter_by_type: Optional[List[str]]) -> Optional[Dict[str, Any]]:
        """Xây dựng filter metadata cho ChromaDB"""
        if not filter_by_type:
            return None
        
        # ChromaDB sử dụng where clauses để filter
        # VD: {"section_type": {"$in": ["dieu", "khoan"]}}
        return {
            "section_type": {"$in": filter_by_type}
        }

    def retrieve(
        self,
        request: ChromaQueryRequest
    ) -> List[ChromaQueryResult]:
        """
        Retrieve điều khoản từ ChromaDB dựa trên query
        
        Args:
            request: ChromaQueryRequest chứa query và các filter
            
        Returns:
            List các ChromaQueryResult được sắp xếp theo similarity score
        """
        # 1. Embed query
        query_vector = self._embed_query(request.query)
        
        # 2. Build filter metadata nếu cần
        # Nếu không chỉ định filter_by_type, tự động filter chỉ lấy leaf nodes
        filter_by_type = request.filter_by_type or LEAF_NODE_TYPES
        filter_metadata = self._build_filter_metadata(filter_by_type)
        
        # 3. Query ChromaDB
        request.query_vector = query_vector  # Gán vector vào request để query
        request.filter = filter_metadata  # Gán filter vào request để query
        chroma_results = self.chroma_store.query(request)
        results = chroma_results if chroma_results else []
        
        # 4. Filter theo score threshold nếu cần
        if request.score_threshold:
            results = [
                r for r in results 
                if r.distance >= request.score_threshold
            ]
        
        return results

    def retrieve_by_query_string(
        self,
        query: str,
        top_k: int = 5,
        filter_by_type: Optional[List[str]] = None,
        score_threshold: Optional[float] = None
    ) -> List[ChromaQueryResult]:
        """
        Helper method để retrieve với query string đơn giản
        
        Args:
            query: Câu truy vấn
            top_k: Số lượng kết quả
            filter_by_type: Lọc theo loại
            score_threshold: Ngưỡng score
            
        Returns:
            List các ChromaQueryResult
        """
        request = ChromaQueryRequest(
            query=query,
            top_k=top_k,
            filter_by_type=filter_by_type,
            score_threshold=score_threshold
        )
        return self.retrieve(request)
