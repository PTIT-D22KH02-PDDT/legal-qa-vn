from typing import List, Callable, Optional, Dict, Any
from pydantic import BaseModel
from src.core.models import DocumentNode
from .schemas import EmbeddingRequest, EmbeddingResult
from .utils import create_chunk_embedding_text

EmbeddingFunction = Callable[[List[EmbeddingRequest]], List[EmbeddingResult]]

class EmbeddingPipeline(BaseModel):
    """Kết nối chunking module và embedding module và triển khai embedding module """
    chunk_documents: List[DocumentNode]
    
    # full_payload: Optional[Dict[str, Any]] = None

    def _to_embedding_requests(self) -> List[EmbeddingRequest]:
        if not self.chunk_documents:
            return []
        if isinstance(self.chunk_documents[0], DocumentNode):
            requests = []
            for stt, chunk in enumerate(self.chunk_documents[1:]):
                text = create_chunk_embedding_text(chunk)
                requests.append(
                    EmbeddingRequest(
                        chunk_id=chunk.id,
                        num_chunk=stt + 1,
                        text=text
                    )
                )
            return requests
        else:
            raise ValueError(f"chunk_documents phải là List[DocumentNode], nhưng nhận {type(self.chunk_documents[0])}")

    def run(self, embed_fn: EmbeddingFunction) -> List[EmbeddingResult]:
        requests = self._to_embedding_requests()
        return embed_fn(requests)