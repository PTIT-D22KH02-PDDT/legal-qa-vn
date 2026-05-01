from typing import List, Callable
from src.core.models import DocumentNode
from .schemas import EmbeddingRequest, EmbeddingResult
from .utils import create_chunk_embedding_text, create_chunk_embedding_metadata

EmbeddingFunction = Callable[[List[EmbeddingRequest]], List[EmbeddingResult]]

class EmbeddingPipeline:
    """Kết nối chunking module và embedding module và triển khai embedding module """
    chunk_documents: List[DocumentNode]
    
    def __init__(self, chunk_documents: List[DocumentNode]):
        self.chunk_documents = chunk_documents

    def _to_embedding_requests(self) -> List[EmbeddingRequest]:
        if not self.chunk_documents:
            return []
        
        if not all(isinstance(doc, DocumentNode) for doc in self.chunk_documents):
            raise ValueError(
                f'chunk_documents phải là list[DocumentNode], nhưng nhận { [type(doc) for doc in self.chunk_documents] }'
            )
        
        requests: list[EmbeddingRequest] = []

        for stt, chunk in enumerate(self.chunk_documents[1:], start=1):
            requests.append(
                EmbeddingRequest(
                    chunk_id=chunk.id,
                    chunk_index=stt,
                    text=create_chunk_embedding_text(chunk),
                    metadata=create_chunk_embedding_metadata(chunk),
                )
            )
        return requests

    def run(self, embed_fn: EmbeddingFunction) -> List[EmbeddingResult]:
        requests = self._to_embedding_requests()
        return embed_fn(requests)
