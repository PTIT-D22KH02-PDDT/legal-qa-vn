import logging
from typing import List, Optional, Dict, Any
from src.indexing.vector_store import ChromaQueryRequest, ChromaQueryResult
from src.indexing.embedding import create_embedding_request
from .reranker import CrossEncoderReranker, RemoteReranker
from dataclasses import dataclass

LEAF_NODE_TYPES = ['dieu', 'khoan', 'diem', 'phu_luc_phan']

logger = logging.getLogger(__name__)

@dataclass
class SearchService:
    """
    SearchService gồm retrieve + rerank (optional)
    
    """
    chroma_store: Any
    embedding_model: Any
    reranker: CrossEncoderReranker | RemoteReranker | None = None
    collection_name: str = "legal_documents"

    def _embed_query(self, query: str) -> List[float]:
        """Embed query thành vector"""
        embedding_request = create_embedding_request(query)
        result = self.embedding_model.embed([embedding_request])
        if not result:
            raise ValueError(f"Failed to embed query: {query}")
        return result[0].vector

    def _build_filter(
            self, 
            filter_by_type: Optional[List[str]]
    ) -> Optional[Dict[str, Any]]:
        """
        Xây dựng metadata filter cho ChromaDB query
        """
        if not filter_by_type:
            return None
        
        # VD: {"section_type": {"$in": ["dieu", "khoan"]}}
        return {
            "section_type": {
                "$in": filter_by_type
            }
        }

    def _retrieve(
        self,
        query: Optional[str] = None,
        query_vector: Optional[List[float]] = None,
        top_k: int = 10,
        metadata_filter: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[ChromaQueryResult]:
        """
        Retrieve điều khoản từ ChromaDB dựa trên query

        Args:
            request: ChromaQueryRequest chứa query, query_vector, top_k, metadata_filter

        Returns:
            Danh sách các ChromaQueryResult được sắp xếp theo độ tương đồng giảm dần
        """

        # 1. Embed query
        if query:
            query_vector = self._embed_query(query)
        elif query_vector is None:
            raise ValueError("Phải cung cấp query hoặc query_vector")

        # 2. Xây bộ lọc metadata
        # Trước mắt là section_type
        filter_metadata = self._build_filter(metadata_filter.get('section_type') if metadata_filter else LEAF_NODE_TYPES)

        # 3. Truy vấn ChromaDB
        request = ChromaQueryRequest(
            query=query,
            query_vector=query_vector,
            top_k=top_k,
            metadata_filter=filter_metadata,
            score_threshold=score_threshold
        )
        
        results = self.chroma_store.query(request) or []
        
        # 4. Filter theo score_threshold
        if score_threshold is not None:
            results = [
                r for r in results if r.distance <= score_threshold
            ]
        
        return results
    
    def search(
            self,
            query: Optional[str] = None,
            query_vector: Optional[List[float]] = None,
            top_k_retrieve: int = 10,
            top_k_rerank: Optional[int] = None,
            metadata_filter: Optional[Dict[str, Any]] = None,
            use_rerank: bool = False,
            score_threshold: Optional[float] = None
    ) -> List[ChromaQueryResult]:
        """
        Search documents

        Args:
            query: Câu truy vấn
            query_vector: Vector truy vấn (nếu có)
            top_k_retrieve: Số lượng kết quả retrieve ban đầu
            top_k_rerank: Số lượng kết quả sau khi rerank
            metadata_filter: Bộ lọc metadata
            use_rerank: Có sử dụng rerank hay không
            score_threshold: Ngưỡng distance để lọc kết quả retrieve
        
        Returns:
            list[ChromaQueryResult]: Danh sách kết quả sau khi retrieve và rerank (nếu có)
        """

        if use_rerank and self.reranker is None:
            raise ValueError("use_rerank=True nhưng không có reranker nào được truyền vào")
        
        # 1. Retrieve
        logger.info(f"Search query={query} with top_k_retrieve={top_k_retrieve}, score_threshold={score_threshold}, rerank={use_rerank}")

        candidates = self._retrieve(
            query=query,
            query_vector=query_vector,
            top_k=top_k_retrieve,
            metadata_filter=metadata_filter,
            score_threshold=score_threshold
        )

        if not candidates:
            logger.info("No candidates retrieved from ChromaDB")
            return []
        
        # 2. Rerank (nếu có)
        if use_rerank and self.reranker:
            if query is None:
                raise ValueError("Reranking requires query text, but query is None")
            logger.info(f"Reranking {len(candidates)} candidates with top_k_rerank={top_k_rerank}")
            reranked_results = self.reranker.rerank(
                query=query,
                documents=candidates,
                top_k=top_k_rerank or len(candidates)
            )
            return reranked_results

        return candidates

    def search_by_section_type(
        self,
        query: str,
        section_type: str,
        top_k_retrieve: int = 10,
        top_k_rerank: Optional[int] = None,
        use_rerank: bool = False,
        score_threshold: Optional[float] = None
    ) -> List[ChromaQueryResult]:
        """
        Search documents với filter theo section_type

        Args:
            query: Câu truy vấn
            section_type: section_type để lọc
            top_k_retrieve: Số lượng kết quả retrieve ban đầu
            top_k_rerank: Số lượng kết quả sau khi rerank
            use_rerank: Có sử dụng rerank hay không
            score_threshold: Ngưỡng distance để lọc kết quả retrieve
        
        Returns:
            list[ChromaQueryResult]: Danh sách kết quả sau khi retrieve và rerank (nếu có)
        """
        metadata_filter = {"section_type": [section_type]}
        return self.search(
            query=query,
            top_k_retrieve=top_k_retrieve,
            top_k_rerank=top_k_rerank,
            metadata_filter=metadata_filter,
            use_rerank=use_rerank,
            score_threshold=score_threshold
    )