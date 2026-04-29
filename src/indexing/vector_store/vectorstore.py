from typing import List, Callable
from pydantic import BaseModel
from src.indexing.embedding import EmbeddingResult
from .schemas import ChromaUpsertRequest
from src.indexing.vector_store.chroma_store import ChromaStore

class VectorStorePipeline(BaseModel):
    """Pipeline để lưu trữ vector vào ChromaDB"""
    embeddings: List[EmbeddingResult]

    def _to_upsert_requests(self) -> List[ChromaUpsertRequest]:
        """Kết nối với EmbeddingResult để tạo dữ liệu upsert cho ChromaDB"""
        requests: List[ChromaUpsertRequest] = []
        for embedding in self.embeddings:
            if not embedding.chunk_id:
                raise ValueError(f"EmbeddingResult thiếu chunk_id: {embedding}")
            metadata = dict(embedding.metadata or {})
            if embedding.num_chunk is not None:
                metadata.setdefault("num_chunk", embedding.num_chunk)

            requests.append(
                ChromaUpsertRequest(
                    chunk_id=embedding.chunk_id,
                    num_chunk=embedding.num_chunk,
                    text=embedding.text,
                    vector=embedding.vector,
                    metadata=metadata
                )
            )
        return requests
    
    def run(self, store: ChromaStore, batch_size: int = None) -> None:
        """Upsert toàn bộ chunks vào ChromaStore"""
        requests = self._to_upsert_requests()
        if batch_size:
            store.upsert_batch(requests, batch_size=batch_size)
        else:
            store.upsert(requests)