"""
Remote API Client để gọi FastAPI server
"""

from typing import List, Dict, Any
import httpx
import numpy as np
from pathlib import Path
import logging

from .config import APIConfig

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Exception for API errors"""
    pass


class RemoteAPIClient:
    """
    Client để gọi remote FastAPI server hosting:
    - Embedding model
    - Cross-encoder Reranker model
    - LLM Generate model
    """
    
    def __init__(self, config: APIConfig = None):
        """
        Args:
            config: APIConfig instance hoặc None để load từ .env
        """
        self.config = config or APIConfig.from_env()
        self.client = httpx.Client(
            timeout=self.config.api_timeout,
            verify=False  # Ignore SSL warnings cho ngrok
        )
        logger.info(f"RemoteAPIClient initialized with timeout={self.config.api_timeout}s")
    
    def _handle_response(self, response: httpx.Response, endpoint: str) -> Dict[str, Any]:
        """Xử lý response từ API"""
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_msg = f"API Error ({endpoint}): {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise APIError(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"Connection Error ({endpoint}): {str(e)}"
            logger.error(error_msg)
            raise APIError(error_msg) from e
    
    def embed(self, texts: List[str]) -> np.ndarray:
        """
        Gọi /embed endpoint để embed danh sách text
        
        Args:
            texts: List of strings to embed
        
        Returns:
            np.ndarray: Embeddings với shape (len(texts), embedding_dim)
        
        Raises:
            APIError: Nếu request thất bại
        """
        if not texts:
            raise ValueError("texts must not be empty")
        
        logger.debug(f"Embedding {len(texts)} texts")
        
        try:
            response = self.client.post(
                self.config.embed_api_url,
                json={"texts": texts},
                timeout=self.config.api_timeout
            )
            data = self._handle_response(response, "embed")
            
            embeddings = np.array(data["embeddings"], dtype=np.float32)
            logger.debug(f"Embedding result shape: {embeddings.shape}")
            return embeddings
        
        except Exception as e:
            logger.error(f"Embedding failed: {str(e)}")
            raise
    
    def embed_requests(self, requests: List) -> List:
        """
        Adapter để nhận List[EmbeddingRequest] và return List[EmbeddingResult]
        Dùng khi thay thế local embedding model
        
        Args:
            requests: List of EmbeddingRequest
        
        Returns:
            List[EmbeddingResult]
        """
        from src.indexing.embedding.schemas import EmbeddingResult
        
        texts = [req.text for req in requests]
        embeddings = self.embed(texts)
        
        results = []
        for i, req in enumerate(requests):
            results.append(EmbeddingResult(
                chunk_id=req.chunk_id,
                num_chunk=req.num_chunk,
                embedding=embeddings[i].tolist(),
                embedding_length=len(embeddings[i])
            ))
        return results
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Gọi /rerank endpoint để xếp hạng lại documents
        
        Args:
            query: Query string
            documents: List of documents to rerank
            top_k: Số lượng top results
        
        Returns:
            List of {"rank": int, "document": str, "score": float}
        
        Raises:
            APIError: Nếu request thất bại
        """
        if not documents:
            raise ValueError("documents must not be empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        
        logger.debug(f"Reranking {len(documents)} documents with query: {query[:50]}")
        
        try:
            response = self.client.post(
                self.config.rerank_api_url,
                json={
                    "query": query,
                    "documents": documents,
                    "top_k": top_k
                },
                timeout=self.config.api_timeout
            )
            data = self._handle_response(response, "rerank")
            
            results = data["results"]
            logger.debug(f"Rerank returned {len(results)} results")
            return results
        
        except Exception as e:
            logger.error(f"Reranking failed: {str(e)}")
            raise
    
    def rerank_pairs(self, pairs: List[tuple], top_k: int = None) -> List[float]:
        """
        Adapter để receive List[Tuple[query, document]] từ CrossEncoderReranker.predict()
        Return List[scores] (sorted by priority theo document order)
        
        Args:
            pairs: List[(query, document), ...]
            top_k: Ignored - chỉ dùng để compatible với CrossEncoderReranker interface
        
        Returns:
            List[scores] theo order của documents input
        """
        if not pairs:
            raise ValueError("pairs must not be empty")
        
        # Tất cả pairs phải có cùng query (assumption từ CrossEncoderReranker)
        query = pairs[0][0]
        documents = [pair[1] for pair in pairs]
        
        # Gọi rerank API
        results = self.rerank(
            query=query,
            documents=documents,
            top_k=len(documents)
        )
        
        # Convert results về format scores theo document order
        # results = [{"rank": int, "document": str, "score": float}, ...]
        score_map = {item["document"]: item["score"] for item in results}
        scores = [score_map.get(doc, 0.0) for doc in documents]
        
        return scores
    
    def generate(
        self,
        prompt: str,
        max_length: int = 200,
        temperature: float = 0.7
    ) -> str:
        """
        Gọi /generate endpoint để generate text
        
        Args:
            prompt: Input prompt
            max_length: Maximum length of generated text
            temperature: Sampling temperature
        
        Returns:
            Generated text
        
        Raises:
            APIError: Nếu request thất bại
        """
        if not prompt:
            raise ValueError("prompt must not be empty")
        
        logger.debug(f"Generating with prompt: {prompt[:50]}")
        
        try:
            response = self.client.post(
                self.config.generate_api_url,
                json={
                    "prompt": prompt,
                    "max_length": max_length,
                    "temperature": temperature
                },
                timeout=self.config.api_timeout
            )
            data = self._handle_response(response, "generate")
            
            answer = data["answer"]
            logger.debug(f"Generated text length: {len(answer)}")
            return answer
        
        except Exception as e:
            logger.error(f"Generation failed: {str(e)}")
            raise
    
    def health_check(self) -> bool:
        """
        Check nếu API server available
        
        Returns:
            True nếu server khỏe, False otherwise
        """
        try:
            response = self.client.get(
                self.config.embed_api_url.rsplit("/", 1)[0] + "/",
                timeout=5.0
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Health check failed: {str(e)}")
            return False
    
    def close(self):
        """Close HTTP client"""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
