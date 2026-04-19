"""Abstract base class for document rerankers."""

from abc import ABC, abstractmethod
from typing import List, Optional
from src.schemas import ChromaQueryResult 
class BaseReranker(ABC):
    """
    Abstract base class for document rerankers.

    Rerankers take a query and a list of retrieved documents, then reorder
    the documents by relevance to the query. This is typically more accurate
    than initial retrieval scoring but slower.

    Implementations can use:
    - Cross-encoder models (e.g., sentence-transformers CrossEncoder)
    - API-based rerankers (e.g., Cohere, Jina)
    - LLM-based rerankers
    """

    @abstractmethod
    def startup(self) -> None:
        """
        Initialize the reranker.

        This includes:
        - Loading model weights
        - Setting up device (CPU/GPU)
        - Warmup inference (if applicable)
        """
        pass

    @abstractmethod
    def rerank(
        self,
        query: str,
        documents: List[ChromaQueryResult],
        top_k: int,
    ) -> List[ChromaQueryResult]:
        """
        Rerank documents by relevance to the query.

        Args:
            query: The user's query/question.
            documents: List of ChromaQueryResult documents to rerank.
            top_k: Number of top documents to return.

        Returns:
            List of top_k documents sorted by relevance (highest first).
        """
        pass

    @property
    @abstractmethod
    def is_initialized(self) -> bool:
        """Check if the reranker has been initialized and is ready to use."""
        pass


"""Vietnamese reranker implementation using transformers."""
import logging
import time
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

import numpy as np
logger = logging.getLogger(__name__)


class VietnameseReranker(BaseReranker):
    """
    Reranker using Vietnamese-specific model: AITeamVN/Vietnamese_Reranker
    
    Features:
    - Optimized for Vietnamese legal documents
    - Efficient batch processing
    - GPU support when available
    - Memory-efficient scoring
    """

    def __init__(
        self,
        model_name: str = "AITeamVN/Vietnamese_Reranker",
        max_length: int = 512,
        device: Optional[str] = None,
        batch_size: int = 32,
    ) -> None:
        """
        Initialize Vietnamese Reranker.
        
        Args:
            model_name: HuggingFace model ID
            max_length: Maximum token length for input pairs
            device: Device to run on ('cuda', 'cpu', or None for auto)
            batch_size: Batch size for scoring
        """
        self.model_name = model_name
        self.max_length = max_length
        self._device = device
        self.batch_size = batch_size
        self._model = None
        self._tokenizer = None
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def startup(self) -> None:
        """Initialize and load the reranker model."""
        if self._initialized:
            return

        logger.info(f"Loading VietnameseReranker: {self.model_name}")
        t_start = time.time()

        # Device detection
        if self._device is not None:
            device = self._device
        else:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        # Log device info
        if device == "cuda":
            try:
                gpu_name = torch.cuda.get_device_name(0)
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
                logger.info(f"Using GPU: {gpu_name} ({gpu_memory:.1f}GB)")
            except Exception:
                logger.info("Using CUDA")
        else:
            logger.warning("Using CPU (slower). Consider using GPU for better performance.")

        try:
            # Load tokenizer
            logger.info("Loading tokenizer...")
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            
            # Load model
            logger.info(f"Loading model on {device}...")
            self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self._model = self._model.to(device)
            self._model.eval()
            
            self._initialized = True
            logger.info(f"Reranker loaded in {time.time() - t_start:.2f}s")

        except Exception as e:
            logger.error(f"Failed to load VietnameseReranker: {e}")
            raise

    def rerank(
        self,
        query: str,
        documents: List[ChromaQueryResult],
        top_k: int,
    ) -> List[ChromaQueryResult]:
        """
        Rerank documents by relevance to query using Vietnamese reranker.
        
        Args:
            query: User's search query
            documents: List of retrieved documents to rerank
            top_k: Number of top documents to return
            
        Returns:
            List of reranked documents (top_k)
        """
        if not self._initialized or self._model is None or self._tokenizer is None:
            raise RuntimeError(
                "VietnameseReranker not initialized. Call startup() first."
            )

        if not documents:
            return []

        logger.info(f"Reranking {len(documents)} documents, returning top {top_k}")
        t_start = time.time()
        
        # Build query-document pairs [query, document_text]
        pairs = [[query, doc.text] for doc in documents]

        # Process in batches
        all_scores = []
        device = next(self._model.parameters()).device
        
        with torch.no_grad():
            for batch_start in range(0, len(pairs), self.batch_size):
                batch_end = min(batch_start + self.batch_size, len(pairs))
                batch_pairs = pairs[batch_start:batch_end]
                
                # Tokenize batch
                inputs = self._tokenizer(
                    batch_pairs,
                    padding=True,
                    truncation=True,
                    return_tensors='pt',
                    max_length=self.max_length
                )
                
                # Move to device
                inputs = {k: v.to(device) for k, v in inputs.items()}
                
                # Get scores (logits)
                outputs = self._model(**inputs, return_dict=True)
                batch_scores = outputs.logits.view(-1,).float().cpu().numpy()
                all_scores.extend(batch_scores)

        scores_array = np.array(all_scores)
        
        # Get top_k indices
        if len(scores_array) > top_k:
            top_indices = np.argsort(scores_array)[::-1][:top_k]
        else:
            top_indices = np.argsort(scores_array)[::-1]

        # Build reranked documents with scores
        top_k_docs = []
        for idx in top_indices:
            doc = documents[idx]
            # Create new ChromaQueryResult with score_rerank
            reranked_doc = ChromaQueryResult(
                chunk_id=doc.chunk_id,
                text=doc.text,
                metadata=doc.metadata,
                distance=doc.distance,
                score_rerank=float(scores_array[idx])
            )
            top_k_docs.append(reranked_doc)

        logger.info(f"Reranking complete in {time.time() - t_start:.4f}s")
        return top_k_docs