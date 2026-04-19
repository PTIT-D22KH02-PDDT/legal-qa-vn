"""
Remote Reranker Adapter - sử dụng reranking từ remote API server
thay vì local Vietnamese reranker model
"""

from typing import List
import logging

from src.api.remote_client import RemoteAPIClient
from src.schemas import ChromaQueryResult
from .base import BaseReranker

logger = logging.getLogger(__name__)


class RemoteReranker(BaseReranker):
    """
    Adapter để sử dụng RemoteAPIClient như một reranker.
    
    Cung cấp interface tương tự như VietnameseReranker
    nhưng thay vì chạy local model, gọi remote API.
    
    Dùng cho SearchPipeline khi muốn sử dụng reranking từ ngrok server.
    """
    
    def __init__(self, api_client: RemoteAPIClient):
        """
        Args:
            api_client: RemoteAPIClient instance
        """
        self.api_client = api_client
        self._initialized = True
        logger.info("RemoteReranker initialized")
    
    @property
    def is_initialized(self) -> bool:
        """RemoteReranker sẵn sàng luôn (không cần load model local)."""
        return self._initialized
    
    def startup(self) -> None:
        """RemoteReranker không cần startup (không load model local)."""
        pass
    
    def rerank(
        self,
        query: str,
        documents: List[ChromaQueryResult],
        top_k: int,
    ) -> List[ChromaQueryResult]:
        """
        Xếp hạng lại tài liệu sử dụng remote API.
        
        Args:
            query: User's search query
            documents: List of ChromaQueryResult to rerank
            top_k: Number of top documents to return
        
        Returns:
            List of reranked ChromaQueryResult (top_k)
        """
        if not documents:
            return []
        
        logger.info(f"Reranking {len(documents)} documents using remote API")
        
        try:
            # Extract document texts for API call
            doc_texts = [doc.text for doc in documents]
            
            # Call remote API
            results = self.api_client.rerank(
                query=query,
                documents=doc_texts,
                top_k=top_k
            )
            
            # Map scores back to original documents
            # results format: [{"rank": int, "document": str, "score": float}, ...]
            score_map = {item["document"]: item["score"] for item in results}
            
            # Build result list with full metadata
            ranked_items = []
            for doc in documents:
                score = score_map.get(doc.text, 0.0)
                ranked_items.append({
                    "doc": doc,
                    "score": score
                })
            
            # Sort by relevance score
            ranked_items.sort(key=lambda x: x["score"], reverse=True)
            
            # Return top_k with updated scores
            result_docs = []
            for idx, item in enumerate(ranked_items[:top_k], start=1):
                doc = item["doc"]
                reranked_doc = ChromaQueryResult(
                    chunk_id=doc.chunk_id,
                    text=doc.text,
                    metadata=doc.metadata,
                    distance=doc.distance,
                    score_rerank=item["score"]
                )
                result_docs.append(reranked_doc)
            
            logger.info(f"Reranking completed. Returned {len(result_docs)} results")
            return result_docs
        
        except Exception as e:
            logger.error(f"Failed to rerank: {str(e)}")
            raise
