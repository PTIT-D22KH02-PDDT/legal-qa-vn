"""
Cross-Encoder Re-ranking Module for Vietnamese Legal Documents

Re-rank retrieved documents using cross-encoder models that evaluate
query-document relevance directly.
"""

from typing import List, Tuple, Optional
import numpy as np
from dataclasses import dataclass
import warnings

try:
    from sentence_transformers import CrossEncoder
except ImportError:
    raise ImportError(
        "sentence-transformers package required for cross-encoder re-ranking. "
        "Install with: pip install sentence-transformers"
    )


@dataclass
class RankedResult:
    """Result item from cross-encoder re-ranking"""
    
    ids: str
    documents: str
    metadatas: dict
    distances: float
    relevance_score: float  # Cross-encoder score [0, 1]
    rank: int


class CrossEncoderReranker:
    """
    Re-rank retrieved documents using Cross-Encoder models.
    
    Cross-encoders evaluate query-document pairs directly,
    providing more accurate relevance scoring than embedding similarity.
    
    Args:
        model_name: HuggingFace model identifier
        device: 'cpu' or 'cuda' for inference
        batch_size: Batch size for inference
        normalize_scores: Normalize scores to [0, 1]
    """
    
    def __init__(
        self,
        model_name: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        device: str = "cpu",
        batch_size: int = 32,
        normalize_scores: bool = True,
    ):
        """Initialize cross-encoder model"""
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.normalize_scores = normalize_scores
        
        # Load model
        self.model = CrossEncoder(model_name, device=device, max_length=512)
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        ids: List[str],
        metadatas: List[dict],
        vector_distances: List[float],
        top_k: Optional[int] = None,
    ) -> List[RankedResult]:
        """
        Re-rank documents based on query relevance.
        
        Args:
            query: Search query
            documents: List of document texts/chunks
            ids: List of document IDs
            metadatas: List of metadata dicts
            vector_distances: Original vector search distances (for reference)
            top_k: Return top-k results. If None, return all ranked.
        
        Returns:
            List of RankedResult objects, sorted by relevance descending
        """
        if not documents:
            return []
        
        # Prepare query-document pairs
        pairs = [[query, doc] for doc in documents]
        
        # Score pairs with cross-encoder
        scores = self.model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        
        # Normalize scores if needed
        if self.normalize_scores:
            if scores.min() < 0:
                # Scores may be raw logits, normalize to [0, 1]
                scores = self._normalize_scores(scores)
            else:
                # Already in range [0, 1]
                scores = np.clip(scores, 0, 1)
        
        # Create ranked results
        results = []
        for rank, (doc_id, doc_text, metadata, vec_dist, score) in enumerate(
            zip(ids, documents, metadatas, vector_distances, scores),
            start=1
        ):
            results.append(
                RankedResult(
                    ids=doc_id,
                    documents=doc_text,
                    metadatas=metadata,
                    distances=vec_dist,
                    relevance_score=float(score),
                    rank=rank,
                )
            )
        
        # Sort by relevance score descending
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # Update ranks after sorting
        for i, result in enumerate(results, start=1):
            result.rank = i
        
        # Return top-k if specified
        if top_k:
            results = results[:top_k]
        
        return results
    
    @staticmethod
    def _normalize_scores(scores: np.ndarray) -> np.ndarray:
        """
        Normalize scores from raw logits to [0, 1].
        
        Uses sigmoid normalization to handle logit-style scores.
        """
        # Sigmoid: converts any value to (0, 1)
        normalized = 1 / (1 + np.exp(-scores))
        return normalized
    
    def rerank_with_vector_search(
        self,
        query: str,
        vector_search_results: dict,
        top_k_rerank: int = 5,
    ) -> List[RankedResult]:
        """
        Re-rank results from vector similarity search.
        
        Convenience wrapper that works with ChromaDB query results dict.
        
        Args:
            query: Original search query
            vector_search_results: Dict from ChromaDB query() with keys:
                - ids: list of document IDs
                - documents: list of document texts
                - metadatas: list of metadata dicts
                - distances: list of distances
            top_k_rerank: Return top-k re-ranked results
        
        Returns:
            List of RankedResult objects, sorted by cross-encoder score
        
        Example:
            >>> from src.retrieval.retrieve import RetrievalService
            >>> from src.retrieval.rerank import CrossEncoderReranker
            >>>
            >>> retriever = RetrievalService()
            >>> reranker = CrossEncoderReranker()
            >>>
            >>> # Vector search (fast, broad)
            >>> results = retriever.retrieve_by_query_string(
            ...     query="bản chất của luật",
            ...     top_k=50
            ... )
            >>>
            >>> # Re-rank with cross-encoder (slow, precise)
            >>> reranked = reranker.rerank_with_vector_search(
            ...     query="bản chất của luật",
            ...     vector_search_results=results,
            ...     top_k_rerank=5
            ... )
            >>>
            >>> for result in reranked:
            ...     print(f"[{result.rank}] Score: {result.relevance_score:.3f}")
            ...     print(f"    ID: {result.ids}")
            ...     print(f"    Document: {result.documents[:100]}...")
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
    
    def batch_rerank(
        self,
        queries: List[str],
        batch_results: List[dict],
        top_k_rerank: int = 5,
    ) -> List[List[RankedResult]]:
        """
        Re-rank multiple batch query results.
        
        Args:
            queries: List of search queries
            batch_results: List of vector search result dicts
            top_k_rerank: Return top-k for each query
        
        Returns:
            List of reranked result lists
        """
        reranked_batch = []
        
        for query, results in zip(queries, batch_results):
            reranked = self.rerank_with_vector_search(
                query=query,
                vector_search_results=results,
                top_k_rerank=top_k_rerank,
            )
            reranked_batch.append(reranked)
        
        return reranked_batch
