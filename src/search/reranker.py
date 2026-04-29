from dataclasses import dataclass, field
from typing import Any, List
import logging
import time
import numpy as np
from src.indexing.vector_store import ChromaQueryResult

logger = logging.getLogger(__name__)

@dataclass
class CrossEncoderReranker:
    """Generic cross-encoder reranker"""

    model_name: str = "AITeamVN/Vietnamese_Reranker"
    max_length: int = 2304
    device: str | None = None
    batch_size: int = 32

    _model: Any = field(default=None, init=False, repr=False)
    _tokenizer: Any = field(default=None, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)        

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def startup(self) -> None:
        if self._initialized:
            return
    
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        logger.info(f"Loading CrossEncoderReranker: {self.model_name}")
        start_time = time.time()

        device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        self._model = self._model.to(device)
        self._model.eval()

        self._initialized = True
        logger.info(f"Reranker loaded in {time.time() - start_time:.2f} seconds")

    def _score_pairs(
        self,
        query: str,
        documents: list[ChromaQueryResult]
    ) -> np.ndarray:
        if self._model is None or self._tokenizer is None:
            raise RuntimeError("Reranker chưa được khởi tạo. Chạy startup() trước đi")
    
        import torch

        pairs = [[query, doc.text] for doc in documents]
        scores: list[float] = []

        device = next(self._model.parameters()).device

        with torch.no_grad():
            for start in range(0, len(pairs), self.batch_size):
                batch_pairs = pairs[start:start + self.batch_size]
                inputs = self._tokenizer(
                    batch_pairs,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt"
                )

                inputs = {k: v.to(device) for k, v in inputs.items()}

                outputs = self._model(**inputs, return_dict=True)
                logits = outputs.logits.float()

                if logits.shape[-1] == 1:
                    batch_scores = logits.squeeze(-1)
                else:
                    batch_scores = logits[:, -1]
                
                scores.extend(batch_scores.cpu().numpy().tolist())
            
        return np.array(scores)
    
    def rerank(
        self,
        query: str,
        documents: list[ChromaQueryResult],
        top_k: int
    ) -> list[ChromaQueryResult]:
        
        if not self._initialized:
            raise RuntimeError("Reranker chưa được khởi tạo. Chạy startup() trước đi")
        
        if not documents:
            return []
        
        top_k = max(1, min(top_k, len(documents)))

        scores = self._score_pairs(query=query, documents=documents)
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        reranked_docs: list[ChromaQueryResult] = []

        for idx in top_indices:
            doc = documents[int(idx)]
            reranked_docs.append(
                ChromaQueryResult(
                    chunk_id=doc.chunk_id,
                    text=doc.text,
                    metadata=doc.metadata,
                    distance=doc.distance,
                    score_rerank=float(scores[idx])
                )
            )

        return reranked_docs

@dataclass
class RemoteReranker:
    """Remote reranker sử dụng rerank host bên ngoài."""

    api_client: Any

    def __post_init__(self) -> None:
        logger.info("RemoteReranker initialized")

    @property
    def is_initialized(self) -> bool:
        return True

    def startup(self) -> None:
        return None

    def rerank(
        self,
        query: str,
        documents: List[ChromaQueryResult],
        top_k: int,
    ) -> List[ChromaQueryResult]:
        if not documents:
            return []

        top_k = max(1, min(top_k, len(documents)))

        logger.info("Reranking %d documents using remote API", len(documents))

        doc_texts = [doc.text for doc in documents]

        try:
            results = self.api_client.rerank(
                query=query,
                documents=doc_texts,
                top_k=top_k,
            )

            result_docs: list[ChromaQueryResult] = []

            for item in results:
                if "index" not in item:
                    raise ValueError(
                        "Remote rerank result missing 'index'. "
                    )

                index = int(item["index"])

                if index < 0 or index >= len(documents):
                    raise ValueError(
                        f"Remote rerank returned invalid index={index}, "
                        f"documents_count={len(documents)}"
                    )

                doc = documents[index]
                score = float(item["score"])

                result_docs.append(
                    ChromaQueryResult(
                        chunk_id=doc.chunk_id,
                        text=doc.text,
                        metadata=doc.metadata,
                        distance=doc.distance,
                        score_rerank=score,
                    )
                )

            logger.info("Reranking completed. Returned %d results", len(result_docs))
            return result_docs

        except Exception as e:
            logger.error("Failed to rerank: %s", e)
            raise