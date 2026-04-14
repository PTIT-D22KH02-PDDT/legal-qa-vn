"""Schemas for vector store module."""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator


# Store in vector database

class ChromaConfig(BaseModel):
    collection_name: str
    persist_directory: Optional[str] = None      # Nơi lưu trữ
    distance_metric: Literal["cosine", "l2", "ip"] = "cosine"  # Khoảng cách sử dụng trong ChromaDB
    is_persist: bool = False

    @model_validator(mode='after')
    def validate_persistence(self):
        if self.is_persist and not self.persist_directory:
            raise ValueError('persist_directory is required when is_persist=True')
        return self

class ChromaUpsertRequest(BaseModel):
    """Dữ liệu cần upsert vào ChromaDB"""
    chunk_id: str
    num_chunk: Optional[int] = None  # Số thứ tự của chunk trong văn bản, dùng để kiểm tra thứ tự khi trả về kết quả embedding
    vector: List[float]         # Lấy từ EmbeddingResult.vector
    text: str                   
    metadata: dict   # Lấy từ ChunkMetadata tương ứng và có thể thêm thông tin khác nếu cần

class ChromaQueryRequest(BaseModel):
    """Yêu cầu truy vấn từ ChromaDB"""
    query_vector: List[float]                   # Embeding của câu truy vấn
    top_k: int = Field(5, gt=0)
    filter: Optional[Dict[str, Any]] = None     # Bộ lọc theo metadata nếu cần

class ChromaQueryResult(BaseModel):
    """Kết quả trả về từ ChromaDB sau khi truy vấn"""
    chunk_id: str
    text: str
    metadata: Optional[dict] = None
    distance: float
    score_rerank: Optional[float] = None  # Điểm số từ reranker (nếu có rerank)