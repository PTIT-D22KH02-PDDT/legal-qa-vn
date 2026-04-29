"""
Remote Embedding Adapter - sử dụng embedding từ remote API server
thay vì local model
"""

from typing import List
import logging
import numpy as np
from tqdm import tqdm

from src.api.remote_client import RemoteAPIClient
from .schemas import EmbeddingRequest, EmbeddingResult

logger = logging.getLogger(__name__)


class RemoteEmbeddingModel:
    """
    Adapter để sử dụng RemoteAPIClient như một embedding model.
    
    Cung cấp interface tương tự như OnnxEmbeddingModel hoặc EmbeddingModel
    nhưng thay vì chạy local, gọi remote API.
    
    Dùng cho indexing pipeline khi muốn sử dụng embedding từ ngrok server.
    """
    
    def __init__(self, api_client: RemoteAPIClient):
        """
        Args:
            api_client: RemoteAPIClient instance
        """
        self.api_client = api_client
        logger.info("RemoteEmbeddingModel initialized")
    
    def embed(self, requests: List[EmbeddingRequest], batch_size: int = 32) -> List[EmbeddingResult]:
        """
        Embed danh sách EmbeddingRequest bằng cách gọi remote API.
        
        Interface tương tự như OnnxEmbeddingModel.embed()
        
        Args:
            requests: List[EmbeddingRequest] - các chunk cần embedding
            batch_size: Kích thước batch cho processing
        
        Returns:
            List[EmbeddingResult] - các kết quả embedding
        
        Raises:
            APIError: Nếu gọi API thất bại
        """
        if not requests:
            return []
        
        num_requests = len(requests)
        logger.debug(f"Embedding {num_requests} requests with batch_size={batch_size}")
        
        results: List[EmbeddingResult] = []
        num_batches = (num_requests + batch_size - 1) // batch_size
        
        # Process in batches with progress bar
        with tqdm(total=num_batches, desc="Embedding batches", unit="batch", miniters=1, mininterval=0) as pbar:
            for batch_start in range(0, num_requests, batch_size):
                batch_end = min(batch_start + batch_size, num_requests)
                batch_requests = requests[batch_start:batch_end]
                batch_size_actual = batch_end - batch_start
                
                # Extract texts từ requests
                texts = [req.text for req in batch_requests]
                
                logger.debug(f"Processing batch {batch_start}-{batch_end} ({batch_size_actual} items)")
                
                try:
                    # Gọi remote API embed
                    embeddings = self.api_client.embed(texts)  # shape: (batch_size, embedding_dim)
                    
                    # Convert to List[EmbeddingResult]
                    for idx, req in enumerate(batch_requests):
                        embedding_vector = embeddings[idx].tolist()
                        
                        result = EmbeddingResult(
                            chunk_id=req.chunk_id,
                            num_chunk=req.num_chunk,
                            text=req.text,
                            vector=embedding_vector,
                            token_count=None,
                            metadata=req.metadata
                        )
                        results.append(result)
                
                except Exception as e:
                    logger.error(f"Failed to embed batch {batch_start}-{batch_end}: {str(e)}")
                    raise
                
                pbar.update(1)
        
        logger.debug(f"Embedding completed. Total results: {len(results)}")
        return results
    
    def encode(
        self,
        texts: List[str],
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False
    ) -> np.ndarray:
        """
        Encode texts (compatible với sentence-transformers interface).
        
        Args:
            texts: List of texts to encode
            convert_to_numpy: Always return as numpy array
            normalize_embeddings: Whether to normalize embeddings (ignored, API handles it)
            show_progress_bar: Ignored
        
        Returns:
            np.ndarray: Embeddings
        """
        if not texts:
            return np.array([])
        
        logger.debug(f"Encoding {len(texts)} texts")
        
        try:
            embeddings = self.api_client.embed(texts)
            
            if convert_to_numpy:
                return np.asarray(embeddings, dtype=np.float32)
            return embeddings
        
        except Exception as e:
            logger.error(f"Failed to encode texts: {str(e)}")
            raise
