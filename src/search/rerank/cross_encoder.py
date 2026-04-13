"""
Module Cross-Encoder để xếp hạng lại tài liệu pháp luật Tiếng Việt

Xếp hạng lại các tài liệu được retrieve bằng cross-encoder models
đánh giá mức độ liên quan giữa query và tài liệu trực tiếp.
"""

from typing import List, Tuple, Optional
import numpy as np
from pathlib import Path

from sentence_transformers import CrossEncoder

from .schemas import RankedResult
from .config import RerankerConfig


class CrossEncoderReranker:
    """
    Xếp hạng lại tài liệu được retrieve bằng mô hình Cross-Encoder.
    
    Cross-encoders đánh giá cặp query-tài liệu trực tiếp,
    cung cấp độ chính xác cao hơn embedding similarity.
    
    Args:
        model_name: Model identifier từ HuggingFace hoặc đường dẫn local
        device: 'cpu' hoặc 'cuda' để inference
        batch_size: Kích thước batch cho inference
        normalize_scores: Chuẩn hóa scores sang [0, 1]
        max_length: Độ dài sequence tối đa
    """
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        device: str = "cpu",
        batch_size: int = 32,
        normalize_scores: bool = True,
        max_length: int = 512,
    ):
        """Khởi tạo cross-encoder model"""
        self.device = device
        self.batch_size = batch_size
        self.normalize_scores = normalize_scores
        self.max_length = max_length
        
        if model_name is None:
            config = RerankerConfig.get_default_config()
            params = config.get_reranker_params()
            model_name = params['model_dir']
            self.device = params.get('device', device)
            self.batch_size = params.get('batch_size', batch_size)
            self.normalize_scores = params.get('normalize_scores', normalize_scores)
            self.max_length = params.get('max_length', max_length)
        
        self.model_name = model_name
        
        model_path = Path(model_name)
        if model_path.exists() and model_path.is_dir():
            # Đường dẫn model local
            print(f"[*] Tải model local từ: {model_name}")
            self.model = CrossEncoder(model_name, device=self.device, max_length=self.max_length)
        else:
            # Tên model từ HuggingFace
            print(f"[*] Tải model từ HuggingFace: {model_name}")
            self.model = CrossEncoder(model_name, device=self.device, max_length=self.max_length)
    
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
        Xếp hạng lại tài liệu dựa trên độ liên quan với query.
        
        Args:
            query: Câu truy vấn
            documents: Danh sách văn bản/chunks tài liệu
            ids: Danh sách ID tài liệu
            metadatas: Danh sách metadata dicts
            vector_distances: Khoảng cách từ vector search ban đầu (tham khảo)
            top_k: Trả về top-k kết quả. Nếu None, trả về tất cả xếp hạng.
        
        Returns:
            Danh sách RankedResult sắp xếp theo độ liên quan giảm dần
        """
        if not documents:
            return []
        
        pairs = [[query, doc] for doc in documents]
        
        # Cho điểm cặp với cross-encoder
        scores = self.model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )

        # Chuẩn hóa scores
        if self.normalize_scores:
            if scores.min() < 0:
                scores = self._normalize_scores(scores)
            else:
                # Đã ở trong khoảng [0, 1]
                scores = np.clip(scores, 0, 1)
        
        # Tạo kết quả xếp hạng
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
        
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # Cập nhật hạng sau khi sắp xếp
        for i, result in enumerate(results, start=1):
            result.rank = i
        
        # Trả về top-k
        if top_k:
            results = results[:top_k]
        
        return results
    
    @staticmethod
    def _normalize_scores(scores: np.ndarray) -> np.ndarray:
        """
        Chuẩn hóa scores từ raw logits sang [0, 1].
        """
        # Sigmoid
        normalized = 1 / (1 + np.exp(-scores))
        return normalized
    
    def rerank_with_vector_search(
        self,
        query: str,
        vector_search_results: dict,
        top_k_rerank: int = 5,
    ) -> List[RankedResult]:
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
            Danh sách RankedResult sắp xếp theo cross-encoder score
        
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
        Xếp hạng lại nhiều batch kết quả query.
        
        Args:
            queries: Danh sách câu truy vấn
            batch_results: Danh sách vector search result dicts
            top_k_rerank: Trả về top-k cho mỗi query
        
        Returns:
            Danh sách các danh sách kết quả xếp hạng lại
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
