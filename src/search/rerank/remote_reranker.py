"""
Remote Reranker Adapter - sử dụng reranking từ remote API server
thay vì local cross-encoder model
"""

from typing import List, Tuple
import logging
import numpy as np

from src.api.remote_client import RemoteAPIClient

logger = logging.getLogger(__name__)


class RemoteReranker:
    """
    Adapter để sử dụng RemoteAPIClient như một reranker.
    
    Cung cấp interface tương tự như CrossEncoderReranker
    nhưng thay vì chạy local cross-encoder, gọi remote API.
    
    Dùng cho SearchPipeline khi muốn sử dụng reranking từ ngrok server.
    """
    
    def __init__(self, api_client: RemoteAPIClient):
        """
        Args:
            api_client: RemoteAPIClient instance
        """
        self.api_client = api_client
        logger.info("RemoteReranker initialized")
    
    def predict(self, pairs: List[Tuple[str, str]], batch_size: int = 32) -> np.ndarray:
        """
        Rank cặp (query, document) bằng remote API.
        
        Interface tương tự như CrossEncoderReranker.predict() từ sentence-transformers:
        - Input: List[(query, doc), ...]
        - Output: np.ndarray scores (float32)
        
        Note: Tất cả pairs phải có cùng query (standard assumption từ CrossEncoderReranker)
        
        Args:
            pairs: List[Tuple[query, document]]
            batch_size: Kích thước batch (ignored, API handles batching)
        
        Returns:
            np.ndarray: Scores cho mỗi document
        
        Raises:
            APIError: Nếu gọi API thất bại
            ValueError: Nếu pairs rỗng
        """
        if not pairs:
            raise ValueError("pairs must not be empty")
        
        # Tất cả pairs phải có cùng query
        query = pairs[0][0]
        documents = [pair[1] for pair in pairs]
        
        logger.debug(f"Reranking {len(documents)} documents with query: {query[:50]}...")
        
        try:
            # Gọi remote rerank API
            results = self.api_client.rerank(
                query=query,
                documents=documents,
                top_k=len(documents)
            )
            
            # results format: [{"rank": int, "document": str, "score": float}, ...]
            # Convert về scores array theo order của documents input
            score_map = {item["document"]: item["score"] for item in results}
            scores = np.array([score_map.get(doc, 0.0) for doc in documents], dtype=np.float32)
            
            logger.debug(f"Reranking completed. Score range: [{scores.min():.4f}, {scores.max():.4f}]")
            return scores
        
        except Exception as e:
            logger.error(f"Failed to rerank: {str(e)}")
            raise
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        ids: List[str],
        metadatas: List[dict],
        vector_distances: List[float],
        top_k: int = None,
    ) -> List[dict]:
        """
        Xếp hạng lại tài liệu (tương tự CrossEncoderReranker.rerank()).
        
        Args:
            query: Query string
            documents: List of documents
            ids: List of document IDs
            metadatas: List of metadata dicts
            vector_distances: List of original vector distances
            top_k: Top-k results
        
        Returns:
            List of dicts with ranking info
        """
        if not documents:
            return []
        
        logger.debug(f"Reranking {len(documents)} documents")
        
        try:
            # Gọi remote API
            results = self.api_client.rerank(
                query=query,
                documents=documents,
                top_k=top_k or len(documents)
            )
            
            # Map scores back to original documents
            score_map = {item["document"]: item["score"] for item in results}
            
            # Build result list with full metadata
            ranked_items = []
            for doc_id, doc_text, metadata, vec_dist in zip(ids, documents, metadatas, vector_distances):
                ranked_items.append({
                    "id": doc_id,
                    "document": doc_text,
                    "metadata": metadata,
                    "vector_distance": vec_dist,
                    "relevance_score": score_map.get(doc_text, 0.0)
                })
            
            # Sort by relevance score
            ranked_items.sort(key=lambda x: x["relevance_score"], reverse=True)
            
            # Add rank
            for i, item in enumerate(ranked_items, start=1):
                item["rank"] = i
            
            # Return top-k
            if top_k:
                ranked_items = ranked_items[:top_k]
            
            return ranked_items
        
        except Exception as e:
            logger.error(f"Failed to rerank: {str(e)}")
            raise
    
    def rerank_with_vector_search(
        self,
        query: str,
        vector_search_results: dict,
        top_k_rerank: int = 5,
    ) -> list:
        """
        Xếp hạng lại kết quả từ vector similarity search.
                
        Args:
            query: Câu truy vấn ban đầu
            vector_search_results: Dict từ ChromaDB query() với keys:
                - ids: danh sách ID tài liệu
                - documents: danh sách văn bản tài liệu
                - metadatas: danh sách metadata dicts
                - distances: danh sách khoảng cách
            top_k_rerank: Trả về top-k kết quả xếp hạng lại
        
        Returns:
            Danh sách result dicts sắp xếp theo cross-encoder score
        """
        results = self.rerank(
            query=query,
            documents=vector_search_results["documents"],
            ids=vector_search_results["ids"],
            metadatas=vector_search_results["metadatas"],
            vector_distances=vector_search_results["distances"],
            top_k=top_k_rerank,
        )
        
        return results
