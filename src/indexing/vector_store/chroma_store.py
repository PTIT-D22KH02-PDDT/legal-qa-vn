import chromadb
from typing import List
from tqdm import tqdm
from .schemas import ChromaConfig, ChromaUpsertRequest, ChromaQueryRequest, ChromaQueryResult

class ChromaStore:
    def __init__(self, config: ChromaConfig):
        self.config = config
        
        if self.config.is_persist:
            self.client = chromadb.PersistentClient(path=self.config.persist_directory)
        else:
            self.client = chromadb.EphemeralClient()
        
        self.collection = self.client.get_or_create_collection(
            name=self.config.collection_name,
            metadata={"hnsw:space": self.config.distance_metric}
        )

    def upsert(self, requests: List[ChromaUpsertRequest]) -> None:
        with tqdm(total=len(requests), desc="Upserting", unit="chunk", leave=False) as pbar:
            self.collection.upsert(
                ids = [r.chunk_id for r in requests],
                embeddings = [r.vector for r in requests],
                documents = [r.text for r in requests],
                metadatas = [r.metadata for r in requests]
            )
            pbar.update(len(requests))
    
    def upsert_batch(self, requests: List[ChromaUpsertRequest], batch_size: int = 30) -> None:
        num_batches = (len(requests) + batch_size - 1) // batch_size
        with tqdm(total=num_batches, desc="Upserting batches", unit="batch", leave=False) as pbar:
            for i in range(0, len(requests), batch_size):
                batch = requests[i: i + batch_size]
                ids = [r.chunk_id for r in batch]
                embeddings = [r.vector for r in batch]
                documents = [r.text for r in batch]
                metadatas = [r.metadata for r in batch]
                self.collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
                pbar.update(1)
    

    def query(self, request: ChromaQueryRequest) -> List[ChromaQueryResult]:
        raw = self.collection.query(
            query_embeddings = [request.query_vector],
            n_results = request.top_k,
            include=['documents', 'metadatas', 'distances'],
            **({'where': request.metadata_filter} if request.metadata_filter else {})
        )
    
        return [
            ChromaQueryResult(
                chunk_id=raw['ids'][0][i],
                text=raw['documents'][0][i],
                metadata=raw['metadatas'][0][i],
                distance=raw['distances'][0][i]
            ) for i in range(len(raw['ids'][0]))
        ]

    def get_by_ids(self, chunk_ids: List[str]) -> List[ChromaQueryResult]:
        """
        Tìm kiếm danh sách các chunk theo chunk_id. Dùng để lấy các chunk được referenced (tham chiếu).
        """
        if not chunk_ids:
            return []

        raw = self.collection.get(
            ids=chunk_ids,
            include=['documents', 'metadatas']
        )
        records = {}
        for chunk_id, document, metadata in zip(raw['ids'], raw['documents'], raw['metadatas']):
            records[chunk_id] = ChromaQueryResult(
                chunk_id=chunk_id,
                text=document,
                metadata=metadata or {},
                distance=None
            )

        return [
            records[chunk_id] for chunk_id in chunk_ids if chunk_id in records
        ]

