from typing import List, Optional, Dict, Any
from src.indexing.vector_store import (
    ChromaQueryRequest,
    ChromaQueryResult,
    ChromaConfig,
)
from src.indexing.embedding import (
    decode_section_id,
    EmbeddingRequest,
    EmbeddingResult,
    create_embedding_request,
)
from src.indexing.embedding.onnx_embedding import OnnxEmbeddingModel
from .schemas import RetrieveQuestionRequest, RetrieveResult
from .config import RetrievalConfig


_config = RetrievalConfig.get_default_config()
_store_params = _config.get_store_params()

COLLECTION_NAME = _store_params['collection_name']
CHROMA_DB_DIR = _store_params['persist_directory']
EMBEDDING_MODEL_DIR = _config.get_embedding_params()['model_dir']

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

    def _extract_section_type(self, section_id: str) -> str:
        """
        Lấy loại section từ section_id
        VD: "phan_5.chuong_xxv.dieu_663.khoan_1" -> "khoan"
        """
        parts = section_id.split('.')
        if not parts:
            return ""
        last_part = parts[-1]
        type_name = last_part.split('_')[0]
        return type_name

    def _build_filter_metadata(self, filter_by_type: Optional[List[str]]) -> Optional[Dict[str, Any]]:
        """Xây dựng filter metadata cho ChromaDB"""
        if not filter_by_type:
            return None
        
        # ChromaDB sử dụng where clauses để filter
        # VD: {"section_type": {"$in": ["dieu", "khoan"]}}
        return {
            "section_type": {"$in": filter_by_type}
        }

    def _process_chroma_results(
        self,
        chroma_results: List[ChromaQueryResult]
    ) -> List[RetrieveResult]:
        """Xử lý kết quả từ ChromaDB thành RetrieveResult"""
        results = []
        
        for chroma_result in chroma_results:
            section_id = chroma_result.chunk_id
            section_type = self._extract_section_type(section_id)
            
            # Trả về distance từ ChromaDB
            distance = chroma_result.distance
            
            result = RetrieveResult(
                section_id=section_id,
                section_display=decode_section_id(section_id),
                text=chroma_result.text,
                distance=distance,
                section_type=section_type,
                metadata=chroma_result.metadata
            )
            results.append(result)
        
        return results

    def _apply_reranking(
        self,
        query: str,
        results: List[RetrieveResult],
        top_k: int
    ) -> List[RetrieveResult]:
        """
        Áp dụng reranking để sắp xếp lại kết quả
        
        Args:
            query: Câu truy vấn gốc
            results: Danh sách kết quả từ ChromaDB
            top_k: Số lượng kết quả cuối cùng muốn lấy
            
        Returns:
            Danh sách kết quả đã được rerank
        """
        if not self.reranker or not self.reranker.is_initialized:
            # Nếu không có reranker, return nguyên bản kết quả
            return results[:top_k]
        
        try:
            # Convert RetrieveResult sang ChromaQueryResult để pass vào reranker
            chroma_results = [
                ChromaQueryResult(
                    chunk_id=r.section_id,
                    text=r.text,
                    metadata=r.metadata,
                    distance=r.distance
                ) for r in results
            ]
            
            # Rerank
            reranked = self.reranker.rerank(
                query=query,
                documents=chroma_results,
                top_k=top_k
            )
            
            # Convert lại thành RetrieveResult
            reranked_results = [
                RetrieveResult(
                    section_id=r.chunk_id,
                    section_display=decode_section_id(r.chunk_id),
                    text=r.text,
                    distance=r.distance,
                    section_type=self._extract_section_type(r.chunk_id),
                    metadata=r.metadata,
                    score_rerank=r.score_rerank
                ) for r in reranked
            ]
            
            return reranked_results
        except Exception as e:
            import logging
            logging.warning(f"Reranking failed, returning original results: {e}")
            return results[:top_k]

    def retrieve(
        self,
        request: RetrieveQuestionRequest
    ) -> List[RetrieveResult]:
        """
        Retrieve điều khoản từ ChromaDB dựa trên query
        
        Args:
            request: RetrieveQuestionRequest chứa query và các filter
            
        Returns:
            List các RetrieveResult được sắp xếp theo similarity score (giảm dần)
        """
        # 1. Embed query
        query_vector = self._embed_query(request.query)
        
        # 2. Build filter metadata nếu cần
        # Nếu không chỉ định filter_by_type, tự động filter chỉ lấy leaf nodes
        filter_by_type = request.filter_by_type or LEAF_NODE_TYPES
        filter_metadata = self._build_filter_metadata(filter_by_type)
        
        # 3. Query ChromaDB - lấy nhiều hơn top_k để có đủ sau khi rerank
        top_k_search = request.top_k * 2 if self.reranker and self.reranker.is_initialized else request.top_k
        chroma_request = ChromaQueryRequest(
            query_vector=query_vector,
            top_k=top_k_search,
            filter=filter_metadata
        )
        chroma_results = self.chroma_store.query(chroma_request)
        
        # 4. Process results
        results = self._process_chroma_results(chroma_results)
        
        # 5. Apply reranking nếu có reranker
        if self.reranker and self.reranker.is_initialized:
            results = self._apply_reranking(
                query=request.query,
                results=results,
                top_k=request.top_k
            )
        else:
            # Nếu không có reranker, chỉ lấy top_k kết quả
            results = results[:request.top_k]
        
        # 6. Filter theo score threshold nếu cần
        if request.score_threshold:
            results = [
                r for r in results 
                if r.distance >= request.score_threshold
            ]
        
        # 7. Sort theo score
        # Nếu có reranking, sort theo score_rerank (cao hơn tốt)
        # Nếu không, sort theo distance (thấp hơn tốt)
        if self.reranker and self.reranker.is_initialized and results and results[0].score_rerank is not None:
            results.sort(key=lambda r: r.score_rerank if r.score_rerank is not None else float('-inf'), reverse=True)
        else:
            results.sort(key=lambda r: r.distance)
        
        return results

    def retrieve_by_query_string(
        self,
        query: str,
        top_k: int = 5,
        filter_by_type: Optional[List[str]] = None,
        score_threshold: Optional[float] = None
    ) -> List[RetrieveResult]:
        """
        Helper method để retrieve với query string đơn giản
        
        Args:
            query: Câu truy vấn
            top_k: Số lượng kết quả
            filter_by_type: Lọc theo loại
            score_threshold: Ngưỡng score
            
        Returns:
            List các RetrieveResult
        """
        request = RetrieveQuestionRequest(
            query=query,
            top_k=top_k,
            filter_by_type=filter_by_type,
            score_threshold=score_threshold
        )
        return self.retrieve(request)

    def retrieve_by_section_type(
        self,
        query: str,
        section_type: str,
        top_k: int = 5,
        score_threshold: Optional[float] = None
    ) -> List[RetrieveResult]:
        """
        Retrieve với lọc theo một loại section cụ thể
        
        Args:
            query: Câu truy vấn
            section_type: Loại section (dieu, khoan, diem, etc)
            top_k: Số lượng kết quả
            score_threshold: Ngưỡng score
            
        Returns:
            List các RetrieveResult
        """
        return self.retrieve_by_query_string(
            query=query,
            top_k=top_k,
            filter_by_type=[section_type],
            score_threshold=score_threshold
        )
